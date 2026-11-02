"""④ 청년 공정성 점검: 나이 변수를 쓰는 모델과 빼는 모델의 연령대별 승인 결과 비교."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("fairness")
A = cm.load_artifacts()
AGES = A["meta"]["age_groups"]
CARD = cm.load_card()

st.title("⚖️ 청년 공정성 점검")
with st.container(border=True):
    st.markdown(
        "**배경** 금융 이력이 짧은 청년·주부 같은 '씬파일러'는 연체가 없어도 중·저신용자로 분류되기 쉽습니다. "
        f"서민금융진흥원은 이들을 위한 대안신용평가 모형 개발에 착수했고({cm.source_link('thinfile')}), "
        f"정교한 모형이 오히려 새로운 배제를 만들 수 있다는 우려도 나옵니다({cm.source_link('altdata')}).\n\n"
        f"**질문** 이 모델은 나이 구간에 점수를 줍니다(32세 이하 {CARD['features']['age']['points']['(-inf, 32.5]']}점, "
        f"64세 이상 {CARD['features']['age']['points']['(63.5, inf]']}점). 나이를 빼면 청년의 승인은 얼마나 늘고, 정확도와 손익은 얼마나 줄까요?"
    )

c1, c2 = st.columns([2, 1])
rate = c1.slider("목표 승인율", 50, 95, 80, step=5, format="%d%%") / 100
only_clean = c2.toggle("연체 이력 없는 사람만 보기", value=True,
                       help="연체가 한 번도 없는데도 나이 때문에 불리한지 보기 위한 필터")


@st.cache_data
def frame(key):
    col = "score"
    d = pd.DataFrame(A["fairness"][key], columns=["age_group", "clean", col, "target", "n"])
    return d


def evaluate(d, rate):
    """전체 신청자에서 목표 승인율이 되는 기준점을 정하고 그룹별 결과를 계산."""
    s = d.groupby("score").n.sum().sort_index(ascending=False).cumsum()
    total = d.n.sum()
    cut = int(s[s >= rate * total].index[0])
    d = d.assign(ok=d.score >= cut)
    return cut, d


rows, summary = [], {}
for key, name in [("with_age", "나이 포함 (현재)"), ("no_age", "나이 제외")]:
    cut, d = evaluate(frame(key), rate)
    sub = d[d.clean == 1] if only_clean else d
    for g in AGES:
        x = sub[sub.age_group == g]
        n, ok = x.n.sum(), x[x.ok].n.sum()
        goods = x[x.target == 0]
        rows.append({"모델": name, "연령대": g, "신청자": n, "승인율": ok / n if n else np.nan,
                     "승인자 부도율": x[x.ok & (x.target == 1)].n.sum() / ok if ok else np.nan,
                     "정상 상환자 거절율": goods[~goods.ok].n.sum() / goods.n.sum() if goods.n.sum() else np.nan})
    summary[name] = cut
res = pd.DataFrame(rows)

# ---------------------------------------------------------------- 핵심 지표
w = res[res.모델 == "나이 포함 (현재)"].set_index("연령대")
o = res[res.모델 == "나이 제외"].set_index("연령대")
gap_w = w.loc["20대", "승인율"] - w.loc["60대+", "승인율"]
gap_o = o.loc["20대", "승인율"] - o.loc["60대+", "승인율"]
curve = A["approval_curves"]
G = sum(r[1] for r in [curve["스코어카드"][-1]])
Bn = sum(r[2] for r in [curve["스코어카드"][-1]])
pick = lambda name: min(curve[name], key=lambda r: abs(r[0] - rate))
gain, loss = 0.10, 0.60
p_w = cm.portfolio(pick("스코어카드")[1], pick("스코어카드")[2], G, Bn, gain, loss)
p_o = cm.portfolio(pick("스코어카드(나이 제외)")[1], pick("스코어카드(나이 제외)")[2], G, Bn, gain, loss)

k = st.columns(4)
k[0].metric("20대 승인율", cm.pct(o.loc["20대", "승인율"]), f"{(o.loc['20대', '승인율'] - w.loc['20대', '승인율']) * 100:+.1f}%p (나이 제외 시)")
k[1].metric("20대–60대+ 승인율 격차", f"{gap_o * 100:+.1f}%p", f"현재 {gap_w * 100:+.1f}%p", delta_color="off")
k[2].metric("AUC 변화", f"{A['model_card']['auc']['스코어카드(나이 제외)']:.3f}",
            f"{(A['model_card']['auc']['스코어카드(나이 제외)'] - A['model_card']['auc']['스코어카드']):+.3f}")
k[3].metric("신청 1억 원당 손익 변화", cm.won(p_o["1인당 손익"]), cm.won(p_o["1인당 손익"] - p_w["1인당 손익"]))

# ---------------------------------------------------------------- 차트
st.subheader("연령대별 승인율" + (" (연체 이력 없는 사람)" if only_clean else ""))
bar = alt.Chart(res).mark_bar().encode(
    x=alt.X("연령대:N", sort=AGES, title=None), xOffset=alt.XOffset("모델:N"),
    y=alt.Y("승인율:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
    color=alt.Color("모델:N", scale=alt.Scale(range=["#8FB8B2", "#1F7A73"]), legend=alt.Legend(orient="top", title=None)),
    tooltip=["모델", "연령대", alt.Tooltip("승인율:Q", format=".1%"), alt.Tooltip("승인자 부도율:Q", format=".1%"),
             alt.Tooltip("정상 상환자 거절율:Q", format=".1%"), alt.Tooltip("신청자:Q", format=",")])
st.altair_chart(bar.properties(height=280), width="stretch")

st.subheader("정상 상환자가 거절되는 비율 (기회 평등 지표)")
st.caption("실제로는 갚았을 사람이 거절된 비율입니다. 그룹 간 차이가 작을수록 '같은 상환 능력이면 같은 결과'에 가깝습니다.")
tbl = res.pivot_table(index="연령대", columns="모델", values=["승인율", "승인자 부도율", "정상 상환자 거절율"]).reindex(AGES)
st.dataframe(tbl.style.format("{:.1%}"), width="stretch")

# ---------------------------------------------------------------- 해석
young_bad_w, young_bad_o = w.loc["20대", "승인자 부도율"], o.loc["20대", "승인자 부도율"]
with st.expander("📌 정리: 공정성과 정확도의 트레이드오프", expanded=True):
    st.markdown(
        f"- 승인율 {cm.pct(rate, 0)} 기준으로 나이를 빼면 20대 승인율은 **{cm.pct(w.loc['20대', '승인율'])}에서 {cm.pct(o.loc['20대', '승인율'])}로** 오르고, "
        f"AUC는 {A['model_card']['auc']['스코어카드']:.3f} → {A['model_card']['auc']['스코어카드(나이 제외)']:.3f}로 소폭 낮아집니다.\n"
        f"- 다만 이 데이터에서 20대의 실제 부도율은 60대 이상보다 높습니다. 그래서 나이를 빼면 20대 승인자의 부도율이 "
        f"{cm.pct(young_bad_w)} → {cm.pct(young_bad_o)}로 오릅니다. **나이가 '편견'이 아니라 다른 변수가 잡지 못한 위험을 대신 반영**하고 있을 수 있습니다.\n"
        "- 그래서 대안은 나이를 그냥 빼는 것이 아니라, 나이가 대신하던 정보(소득 안정성, 통신·공과금 납부 이력 등)를 "
        "**직접 측정하는 대안 데이터**를 추가하는 것입니다. 정부가 씬파일러용 대안신용평가를 개발하는 이유와 같습니다.\n"
        "- AI 기본법상 신용평가는 고영향 AI입니다. 이 화면처럼 **그룹별 결과를 정기적으로 점검하고 기록**하는 것이 위험관리 의무의 한 형태입니다."
    )
st.caption(f"기준점: 나이 포함 {summary['나이 포함 (현재)']}점, 나이 제외 {summary['나이 제외']}점 (두 모델 모두 전체 승인율 {cm.pct(rate, 0)}가 되도록 설정). "
           "손익은 순이익률 10%, 손실률 60% 가정.")
cm.sidebar_note()

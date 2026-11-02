"""② 승인 정책 시뮬레이터: 금융사 입장에서 기준점·마진·손실률을 바꾸며 손익을 본다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("policy")
A = cm.load_artifacts()
T = cm.score_table()
G, B = int(T.good.sum()), int(T.bad.sum())

st.title("🏦 승인 정책 시뮬레이터")
st.caption("금융사 리스크 담당자 입장에서 '몇 점부터 승인할지'를 정합니다. "
           f"테스트셋 {G + B:,}명(부도율 {cm.pct(B / (G + B))})에 정책을 적용했을 때의 결과입니다.")

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    margin = c1.slider("대출 1건 순이익률 (%)", 2, 20, 10, help="정상 상환 시 원금 대비 남는 이익 (이자 − 조달·운영비용)")
    lgd = c2.slider("부도 시 손실률 LGD (%)", 20, 100, 60, help="부도가 나면 원금 중 회수하지 못하는 비율")
    cutoff = c3.slider("승인 기준점", 480, 620, cm.load_policy()["approve_cutoff"])
gain, loss = cm.unit_economics(margin, lgd)

curve = cm.cutoff_curve(T, gain, loss)
best = curve.loc[curve["1인당 손익"].idxmax()]
appr = T[T.score >= cutoff]
now = cm.portfolio(appr.good.sum(), appr.bad.sum(), G, B, gain, loss)
base = cm.portfolio(G, B, G, B, gain, loss)
opt_rows = T[T.score >= best.cutoff]
opt = cm.portfolio(opt_rows.good.sum(), opt_rows.bad.sum(), G, B, gain, loss)

k = st.columns(5)
k[0].metric("승인율", cm.pct(now["승인율"]))
k[1].metric("승인자 부도율", cm.pct(now["승인자 부도율"]), f"{(now['승인자 부도율'] - base['승인자 부도율']) * 100:+.1f}%p",
            delta_color="inverse")
k[2].metric("부도 차단율", cm.pct(now["부도 차단율"]))
k[3].metric("정상 고객 거절율", cm.pct(now["정상 거절율"]))
k[4].metric("신청 1억 원당 손익", cm.won(now["1인당 손익"]), cm.won(now["1인당 손익"] - base["1인당 손익"]),
            help="delta는 전원 승인 대비 차이")

if abs(cutoff - best.cutoff) <= 2:
    st.success(f"현재 기준점 {cutoff}점은 손익 최대점({best.cutoff:.0f}점) 근처입니다.")
else:
    diff = opt["1인당 손익"] - now["1인당 손익"]
    st.warning(f"이 조건(순이익률 {margin}%, 손실률 {lgd}%)에서 손익이 가장 큰 기준점은 **{best.cutoff:.0f}점** "
               f"(승인율 {cm.pct(opt['승인율'])})입니다. 지금보다 신청 1억 원당 **{cm.won(diff)}** 더 남습니다.")

# ---------------------------------------------------------------- 손익 곡선
st.subheader("기준점별 손익과 승인율")
plot = curve[(curve.cutoff >= 440) & (curve.cutoff <= 630)].copy()
plot["손익(만 원)"] = plot["1인당 손익"] * 1e4
base_chart = alt.Chart(plot).encode(x=alt.X("cutoff:Q", title="승인 기준점", scale=alt.Scale(domain=[440, 630])))
line = base_chart.mark_line(strokeWidth=3, color="#1F7A73").encode(
    y=alt.Y("손익(만 원):Q", title="신청 1억 원당 손익 (만 원)"),
    tooltip=[alt.Tooltip("cutoff:Q", title="기준점"), alt.Tooltip("손익(만 원):Q", format=",.0f"),
             alt.Tooltip("승인율:Q", format=".1%"), alt.Tooltip("승인자 부도율:Q", format=".1%")])
rules = alt.Chart(pd.DataFrame({"x": [cutoff, best.cutoff], "label": ["현재", "손익 최대"]})).mark_rule(
    strokeDash=[5, 4]).encode(x="x:Q", color=alt.Color("label:N", scale=alt.Scale(domain=["현재", "손익 최대"], range=["#E4572E", "#5B6B7A"]),
                                                       legend=alt.Legend(title=None, orient="top")))
st.altair_chart((line + rules).properties(height=300), width="stretch")
st.caption("이 화면은 테스트셋에서 바로 최적점을 찾습니다. 분석 노트북은 과적합을 막으려고 검증셋에서 기준점(539점)을 고른 뒤 테스트셋으로 평가했기 때문에 숫자가 조금 다릅니다.")

# ---------------------------------------------------------------- 손실률 민감도
st.subheader("손실 구조가 바뀌면 최적 기준점도 바뀐다")
rows = []
for l in [30, 45, 60, 75, 90]:
    for m in [5, 10, 15]:
        c = cm.cutoff_curve(T, m / 100, l / 100)
        b = c.loc[c["1인당 손익"].idxmax()]
        rows.append({"손실률": f"{l}%", "순이익률": f"{m}%", "최적 기준점": int(b.cutoff), "승인율": b["승인율"]})
sens = pd.DataFrame(rows)
heat = alt.Chart(sens).mark_rect().encode(
    x=alt.X("순이익률:N", sort=["5%", "10%", "15%"]), y=alt.Y("손실률:N", sort=["30%", "45%", "60%", "75%", "90%"]),
    color=alt.Color("승인율:Q", scale=alt.Scale(scheme="teals"), legend=alt.Legend(format=".0%")),
    tooltip=["손실률", "순이익률", "최적 기준점", alt.Tooltip("승인율:Q", format=".1%")])
text = heat.mark_text(fontSize=13).encode(text=alt.Text("최적 기준점:Q"), color=alt.value("#15202B"))
c1, c2 = st.columns([3, 2])
c1.altair_chart((heat + text).properties(height=230), width="stretch")
c2.markdown("칸 안의 숫자는 **손익이 최대가 되는 기준점**, 색은 그때의 **승인율**입니다.\n\n"
            "손실률이 높고 마진이 얇을수록 기준점을 올려 덜 승인해야 합니다. "
            "'승인율 80%' 같은 고정 목표보다 **상품의 손실 구조에 맞춘 기준점**이 낫다는 뜻입니다.")

# ---------------------------------------------------------------- 모델 비교
st.subheader("같은 승인율에서 모델 비교")
rate = round(now["승인율"] / 0.005) * 0.005
comp = []
for name, cur in A["approval_curves"].items():
    r = min(cur, key=lambda x: abs(x[0] - rate))
    p = cm.portfolio(r[1], r[2], G, B, gain, loss)
    comp.append({"모델": name, "승인된 부도자": r[2], "승인자 부도율": cm.pct(p["승인자 부도율"], 2),
                 "신청 1억 원당 손익": cm.won(p["1인당 손익"]), "AUC": f"{A['model_card']['auc'][name]:.3f}"})
st.dataframe(pd.DataFrame(comp), hide_index=True, width="stretch")
st.caption(f"모두 승인율 {cm.pct(rate)} 기준. LightGBM은 정확도가 가장 높지만 차이가 크지 않고 거절 사유를 점수표로 설명할 수 없어, "
           "운영 모델은 스코어카드, LightGBM은 비교용(챌린저) 모델로 둡니다.")
cm.sidebar_note()

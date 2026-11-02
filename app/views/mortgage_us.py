"""미국 주택담보대출 부도 분석 (Freddie Mac 2021~2023, 2026.10 공개 데이터)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402
import mortgage_model as mm  # noqa: E402

cm.identify()
cm.page_view("mortgage_us")


@st.cache_resource
def load():
    return (json.loads((cm.ROOT / "models/mortgage_scorecard.json").read_text()),
            json.loads((cm.ROOT / "models/mortgage_artifacts.json").read_text()))


CARD, A = load()
CAL = A["calibration"]

st.title("🏘️ 금리 급등기 미국 주택담보대출 분석")
st.caption("미국 주택금융공사 프레디맥(Freddie Mac)이 2026년 10월 공개한 **실제 주택담보대출 15만 건**(2021~2023년 실행, "
           "2026년 6월까지의 월별 상환 기록)으로 만든 부도 예측 모델입니다. 한국 공개 데이터에는 개인별 실제 연체 결과가 없어 미국 데이터를 썼습니다.")

# ---------------------------------------------------------------- 금리 급등 전후
v = pd.DataFrame(A["vintage"])
k = st.columns(3)
for i, r in v.iterrows():
    k[i].metric(f"{int(r.vintage)}년 대출", f"부도율 {r['부도율'] * 100:.2f}%",
                f"금리 중앙값 {r['금리_중앙값']:.2f}% · DTI {r['DTI_중앙값']:.0f}", delta_color="off")
st.markdown(f"금리 중앙값이 {v['금리_중앙값'].iloc[0]:.2f}%에서 **{v['금리_중앙값'].iloc[-1]:.2f}%로** 오르는 동안 24개월 부도율은 "
            f"**{v['부도율'].iloc[-1] / v['부도율'].iloc[0]:.1f}배**가 됐습니다. (부도 = 첫 납부 후 24개월 안에 90일 이상 연체 또는 부실 정리, 코로나 상환유예·재난 기간 제외)")

tab1, tab2, tab3 = st.tabs(["🧮 부도 위험 계산기", "📊 무엇이 위험을 가르나", "💵 손실 시나리오별 승인 정책"])

with tab1:
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        fico = c1.slider("신용점수 (FICO)", 580, 850, 740)
        dti = c2.slider("DTI (%)", 1, 50, 38, help="월 부채상환액 ÷ 월소득. 한국 DSR과 비슷한 개념")
        ltv = c3.slider("LTV (%)", 5, 97, 80)
        c1, c2, c3 = st.columns(3)
        amount = c1.number_input("대출금액 (달러)", 30000, 1500000, 300000, step=10000)
        spread = c2.slider("같은 시기 평균 대비 금리 차이 (%p)", -1.5, 2.0, 0.0, step=0.125,
                           help="위험할수록 금리를 더 받습니다. 금리 '수준'은 시기마다 달라서 가산폭만 씁니다.")
        borrowers = c3.radio("차주 수", ["1", "2+"], format_func=lambda x: mm.CAT_KO["borrowers"][x], horizontal=True)
        c1, c2, c3 = st.columns(3)
        purpose = c1.selectbox("대출 목적", ["P", "N", "C"], format_func=lambda x: mm.CAT_KO["purpose"][x])
        occupancy = c2.selectbox("거주 형태", ["P", "I", "S"], format_func=lambda x: mm.CAT_KO["occupancy"][x])
        program = c3.selectbox("정책 프로그램", ["none", "H", "F"], format_func=lambda x: mm.CAT_KO["program"][x])
    vals = {"fico": fico, "dti": dti, "ltv": ltv, "rate_spread": spread, "log_upb": np.log10(amount),
            "borrowers": borrowers, "purpose": purpose, "occupancy": occupancy, "program": program}
    score, detail = mm.score_one(CARD, vals)
    pd_old = float(mm.to_pd([score], CARD["scaling"])[0])
    lo = np.log(pd_old / (1 - pd_old)) + CAL["shift_logodds"]
    pd_new = 1 / (1 + np.exp(-lo))
    k = st.columns(3)
    k[0].metric("점수", f"{score}점")
    k[1].metric("24개월 부도 확률 (2023 재보정)", f"{pd_new:.2%}", f"재보정 전 {pd_old:.2%}", delta_color="off")
    k[2].metric("전체 평균 대비", f"{pd_new / CAL['act_oot']:.1f}배", help=f"2023년 실제 평균 부도율 {CAL['act_oot']:.2%}")
    contrib = pd.DataFrame([{"항목": CARD["features"][f]["label_ko"], "평균 대비": d["points"] - CARD["features"][f]["default_points"]}
                            for f, d in detail.items()]).sort_values("평균 대비")
    st.altair_chart(alt.Chart(contrib).mark_bar().encode(
        x=alt.X("평균 대비:Q", title="점수 기여 (0 = 평균)"), y=alt.Y("항목:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
        color=alt.condition("datum['평균 대비'] < 0", alt.value("#E4572E"), alt.value("#1F7A73")),
        tooltip=["항목", "평균 대비"]).properties(height=260), width="stretch")
    st.caption(f"재보정: 2021~22년 기준으로 만든 모델이 2023년 부도를 약 {1 - CAL['pred_oot'] / CAL['act_oot']:.0%} 낮게 예측해, "
               f"절편을 최신 실적에 맞췄습니다(점수로 약 {CAL['shift_logodds'] * CARD['scaling']['pdo'] / np.log(2):.0f}점).")

with tab2:
    c1, c2 = st.columns(2)
    f = pd.DataFrame(A["fico"]).rename(columns={"fico": "FICO"})
    c1.markdown("**신용점수별 부도율**")
    c1.altair_chart(alt.Chart(f).mark_bar(color="#1F7A73").encode(
        x=alt.X("FICO:N", sort=None), y=alt.Y("부도율:Q", axis=alt.Axis(format="%")),
        tooltip=["FICO", alt.Tooltip("부도율:Q", format=".2%"), alt.Tooltip("대출수:Q", format=",")]).properties(height=240), width="stretch")
    dt = pd.DataFrame(A["dti"]).rename(columns={"dti": "DTI"})
    dt["구분"] = ["40 이하"] * 4 + ["40 초과"] * (len(dt) - 4)
    c2.markdown("**DTI별 부도율**")
    c2.altair_chart(alt.Chart(dt).mark_bar().encode(
        x=alt.X("DTI:N", sort=None), y=alt.Y("부도율:Q", axis=alt.Axis(format="%")),
        color=alt.Color("구분:N", scale=alt.Scale(range=["#8FB8B2", "#E4572E"]), legend=None),
        tooltip=["DTI", alt.Tooltip("부도율:Q", format=".2%"), alt.Tooltip("대출수:Q", format=",")]).properties(height=240), width="stretch")
    ft = A["first_time"]
    st.markdown(
        f"- **DTI가 40을 넘으면 부도율이 뚜렷이 오릅니다.** 한국 은행권 DSR 한도 40%의 근거를 미국 실제 데이터로 확인할 수 있습니다.\n"
        f"- **생애최초 구입자 자체는 위험하지 않습니다.** 단순 비교로는 부도율이 {ft['raw_gap'] * 100:+.2f}%p 높지만, "
        f"신용점수·LTV가 같은 사람끼리 비교하면 {ft['adjusted_gap'] * 100:+.2f}%p로 차이가 사라집니다. 위험은 첫 구입이 아니라 낮은 신용점수·높은 LTV에서 옵니다.\n"
        f"- **금리는 수준이 아니라 가산폭으로 봐야 합니다.** 원시 금리를 그대로 쓰면 학습 시기와 2023년의 분포 차이가 PSI {A['psi']['raw_rate']:.2f}로 "
        f"심각하지만, 같은 분기 대비 가산폭은 {A['psi']['rate_spread']:.2f}입니다."
    )
    st.markdown("**모델 성능 (2023년 대출 = 학습에 쓰지 않은 미래 데이터)**")
    perf = pd.DataFrame(A["perf"]).set_index("model")[["AUC", "KS"]]
    st.dataframe(perf.style.format("{:.3f}"), width="stretch")

with tab3:
    agg = pd.DataFrame(A["score_agg_oot"]).sort_values("score", ascending=False)
    c1, c2 = st.columns(2)
    lgd = c1.slider("부도 시 손실률 LGD (%)", 0.5, 60.0, 40.0, step=0.5,
                    help="부도 대출 원금 중 회수하지 못하는 비율") / 100
    margin = c2.slider("대출 원금 대비 연 순이익률 (%)", 0.25, 3.0, 1.0, step=0.25) / 100
    agg["gain"] = (agg.upb - agg.upb_bad) * margin * 2
    agg["loss"] = agg.upb_bad * lgd
    agg["cum_profit"] = (agg.gain - agg.loss).cumsum()
    agg["approval"] = agg.n.cumsum() / agg.n.sum()
    total_upb = agg.upb.sum()
    agg["profit_per_m"] = agg.cum_profit / total_upb * 1e6
    best = agg.loc[agg.profit_per_m.idxmax()]
    all_ok = agg.profit_per_m.iloc[-1]
    k = st.columns(3)
    k[0].metric("손익이 가장 큰 기준점", f"{int(best.score)}점")
    k[1].metric("그때 승인율", f"{best.approval:.1%}")
    k[2].metric("대출 100만 달러당 손익", f"${best.profit_per_m:,.0f}", f"전원 승인 대비 ${best.profit_per_m - all_ok:+,.0f}")
    st.altair_chart(alt.Chart(agg).mark_line(color="#1F7A73", strokeWidth=3).encode(
        x=alt.X("approval:Q", title="승인율", axis=alt.Axis(format="%")),
        y=alt.Y("profit_per_m:Q", title="대출 100만 달러당 2년 손익 ($)"),
        tooltip=[alt.Tooltip("score:Q", title="기준점"), alt.Tooltip("approval:Q", format=".1%"),
                 alt.Tooltip("profit_per_m:Q", format=",.0f")]).properties(height=260), width="stretch")
    L = A["loss"]
    st.markdown(
        f"**실제 손실 데이터**: 24개월 안에 부도 난 대출 {int(L['부도 대출 수']):,}건 중 2026년 6월까지 실제로 청산된 것은 "
        f"**{L['2026.6까지 청산된 비율']:.0%}뿐**이고, 청산되더라도 손실률은 **{L['청산 시 손실률(금액가중)']:.0%} 수준**이었습니다(집값 상승기). "
        f"이 실적대로라면 거의 전원 승인이 최적이지만, 손실률을 위기 수준(40%)으로 올리면 기준점을 높여야 합니다. "
        "그래서 정책은 최근 실적보다 **스트레스 시나리오**로 정합니다. 한국의 스트레스 DSR도 같은 발상입니다."
    )
    st.caption("프레디맥이 매입한(이미 승인된) 대출만 있어, 이 분석은 '승인된 대출 중 어디까지 더 걸러낼지'를 보여줍니다. 순이익률은 가정값입니다.")

st.caption(f"데이터: [Freddie Mac Single-Family Loan-Level Dataset](https://freddiemac.com/research/datasets/sf-loanlevel-dataset) Release 48 (2026.10), "
           f"연도별 무작위 5만 건 샘플. 학습 {A['meta']['n_dev']:,}건(2021~22), 미래 검증 {A['meta']['n_oot']:,}건(2023). 비상업·연구 목적 이용.")
st.sidebar.caption("이 화면은 Freddie Mac 2021~2023년 실제 주택담보대출 15만 건(2026.10 공개)으로 만든 분석입니다. 미국 데이터이며 한국 대출 심사와 다릅니다.")

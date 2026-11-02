"""v3 · 주담대 한도 계산기: 6·27, 10·15 대책과 스트레스 DSR을 한 번에 반영."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("v3_mortgage")
R = cm.load_rules()
SD, MG = R["stress_dsr"], R["mortgage"]
fc = cm.fc

st.title("🏠 주담대 한도 계산기")
st.caption("집값·소득·기존 대출을 넣으면 **LTV, 집값별 상한, 스트레스 DSR** 세 가지 규제 중 무엇 때문에 한도가 정해지는지 보여줍니다. "
           "2025년 6·27, 10·15 대책과 2026년 지방 유예 연장까지 반영했습니다.")

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    region_name = c1.selectbox("지역", list(MG["regions"]))
    price = c2.number_input("집값 (억 원)", 0.5, 100.0, 9.0 if "서울" in region_name else 5.0, step=0.5) * 1e8
    first = c3.toggle("생애최초 구입", value=False)
    c1, c2, c3 = st.columns(3)
    income = c1.number_input("연소득 (만 원)", 0, 100000, 6000, step=100) * 1e4
    lender = c2.radio("대출 기관", ["은행", "2금융권"], horizontal=True)
    rtype = c3.selectbox("금리 유형", list(SD["type_ratio"]), index=1)
    c1, c2, c3 = st.columns(3)
    rate = c1.number_input("예상 대출금리 (연 %)", 1.0, 15.0, 4.2, step=0.1, format="%.2f")
    region = MG["regions"][region_name]
    max_term = region["max_term_years"] or 50
    term = c2.number_input("만기 (년)", 5, max_term, min(30, max_term),
                           help="수도권·규제지역은 최장 30년" if region["max_term_years"] else None)
    st.markdown("**기존 대출** (DSR에 합산)")
    c1, c2, c3 = st.columns(3)
    credit_bal = c1.number_input("신용대출 잔액 (만 원)", 0, 50000, 0, step=100) * 1e4
    credit_rate = c2.number_input("신용대출 금리 (%)", 0.0, 20.0, 6.0, step=0.1)
    other = c3.number_input("그 밖의 대출 월 상환액 (만 원)", 0, 1000, 0, step=5) * 1e4

existing = fc.existing_annual_payment(credit_bal, credit_rate, other, SD["credit_loan_dsr_term_years"])
stress = SD["stress_rate"][region["stress_key"]]
ratio = SD["type_ratio"][rtype]
res = fc.mortgage_limit(price, income, rate, term * 12, region, first, existing, stress, ratio,
                        SD["dsr_cap"][lender], MG["price_caps"])
if st.session_state.get("mort_logged") != (region_name, res["binding"]):
    st.session_state["mort_logged"] = (region_name, res["binding"])
    cm.track("mortgage_calc", region=region_name, binding=res["binding"], first_time=bool(first))

st.divider()
k = st.columns(4)
k[0].metric("예상 최대 한도", cm.eok(res["limit"]), help=cm.krw(res["limit"]))
k[1].metric("한도를 정한 규제", res["binding"])
k[2].metric("월 상환액 (최대 한도 시)", cm.krw(res["monthly_payment"]))
k[3].metric("필요 자기자금", cm.eok(max(price - res["limit"], 0)), help=f"{cm.krw(max(price - res['limit'], 0))} = 집값 − 대출 한도. 취득세·중개수수료 등은 별도입니다.")

lim = pd.DataFrame({
    "규제": [f"LTV {res['ltv_pct']}%", "집값별 상한", f"DSR {SD['dsr_cap'][lender]}% (스트레스 반영)"],
    "한도(억)": [res["by_ltv"] / 1e8, (res["by_cap"] if res["by_cap"] != float("inf") else 0) / 1e8, res["by_dsr"] / 1e8],
    "표시": [cm.krw(res["by_ltv"]), cm.krw(res["by_cap"]), cm.krw(res["by_dsr"])],
})
lim["구분"] = ["binding" if n.startswith({"LTV": "LTV", "가격 상한": "집값", "DSR": "DSR"}[res["binding"]]) else "other" for n in lim.규제]
lim = lim[~((lim.규제 == "집값별 상한") & (res["by_cap"] == float("inf")))]
bar = alt.Chart(lim).mark_bar(cornerRadiusEnd=4).encode(
    y=alt.Y("규제:N", sort=None, title=None, axis=alt.Axis(labelLimit=240)), x=alt.X("한도(억):Q", title="한도 (억 원)"),
    color=alt.Color("구분:N", scale=alt.Scale(domain=["binding", "other"], range=["#E4572E", "#8FB8B2"]), legend=None),
    tooltip=["규제", "표시"])
txt = bar.mark_text(align="left", dx=6, color="#15202B").encode(text="표시:N")
st.altair_chart((bar + txt).properties(height=60 * len(lim) + 20), width="stretch")
st.caption("가장 짧은 막대(빨간색)가 실제 한도입니다." + ("" if region["price_caps"] else " 지방은 집값별 상한이 없습니다."))

c1, c2 = st.columns(2)
with c1:
    st.markdown("**스트레스 금리가 줄인 금액**")
    st.markdown(f"한도 계산 금리 = {rate:.2f}% + 스트레스 {stress}% × {int(ratio * 100)}% = **{rate + res['applied_stress']:.2f}%**")
    st.metric("스트레스 DSR로 줄어든 한도", cm.krw(res["stress_loss"]))
    if ratio > 0 and rtype == "변동형":
        alt_r = fc.mortgage_limit(price, income, rate, term * 12, region, first, existing, stress,
                                  SD["type_ratio"]["혼합형(5년 고정)"], SD["dsr_cap"][lender], MG["price_caps"])
        if alt_r["limit"] > res["limit"]:
            st.info(f"같은 금리의 **혼합형(5년 고정)을** 고르면 스트레스 반영이 80%로 줄어 한도가 **{cm.krw(alt_r['limit'] - res['limit'])}** 늘어납니다.")
with c2:
    st.markdown("**소득별 최대 한도**")
    rows = []
    for inc in [3000, 4000, 5000, 6000, 8000, 10000, 15000]:
        r = fc.mortgage_limit(price, inc * 1e4, rate, term * 12, region, first, existing, stress, ratio,
                              SD["dsr_cap"][lender], MG["price_caps"])
        rows.append({"연소득": f"{inc:,}만", "한도": cm.krw(r["limit"]), "제한 요인": r["binding"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

with st.expander("📋 이 지역에 적용되는 규칙", expanded=False):
    lines = [f"- **LTV**: 무주택 {region['ltv_no_house']}%, 생애최초 {region['ltv_first_time']}%"]
    if region["price_caps"]:
        lines.append("- **집값별 주담대 상한**: 15억 이하 6억 · 15~25억 4억 · 25억 초과 2억 (10·15 대책)")
        lines.append(f"- **전입 의무**: {MG['move_in_months']}개월 이내 · **만기** 최장 {region['max_term_years']}년")
    lines.append(f"- **스트레스 금리**: {stress}% ({region['stress_key']}) · 금리 유형별 반영: " +
                 ", ".join(f"{k} {int(v * 100)}%" for k, v in SD["type_ratio"].items()))
    lines.append(f"- **DSR 한도**: 은행 {SD['dsr_cap']['은행']}%, 2금융권 {SD['dsr_cap']['2금융권']}% · 신용대출은 {SD['credit_loan_dsr_term_years']}년 분할상환으로 가정해 합산")
    lines.append("- 1주택 이상 보유자의 추가 주택 구입용 주담대는 수도권·규제지역에서 금지 (기존 주택 6개월 내 처분 시 예외)")
    st.markdown("\n".join(lines))
cm.rule_sources("mortgage", "대출 규제 근거")
cm.rule_sources("stress_dsr", "스트레스 DSR 근거")
st.caption("정책대출(디딤돌·보금자리론 등)은 별도 한도·금리 기준이 있어 이 계산에 포함하지 않았습니다.")
cm.v3_disclaimer()
cm.sidebar_note()

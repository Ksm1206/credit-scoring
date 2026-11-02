"""v3 · 대출 갈아타기 계산기: 중도상환수수료까지 따져서 실제로 이득인지."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("v3_refinance")
R = cm.load_rules()
PF = R["prepayment_fee"]
fc = cm.fc

st.title("🔄 대출 갈아타기 계산기")
st.caption("더 낮은 금리로 갈아탈 때 **중도상환수수료와 부대비용을 빼고도 남는지**, 몇 달 만에 본전을 찾는지 계산합니다. "
           "대출비교 앱에서 본 금리를 넣어 보세요.")

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    kind = c1.selectbox("대출 종류", ["신용대출", "주택담보대출", "전세대출"])
    balance = c2.number_input("남은 원금 (만 원)", 100, 200000, 5000 if kind == "신용대출" else 30000, step=100) * 1e4
    method = c3.selectbox("상환 방식", cm.fc.METHODS, index=2 if kind in ("신용대출", "전세대출") else 0)
    c1, c2, c3 = st.columns(3)
    cur_rate = c1.number_input("지금 금리 (연 %)", 0.0, 20.0, 6.5 if kind == "신용대출" else 4.8, step=0.1, format="%.2f")
    new_rate = c2.number_input("갈아탈 금리 (연 %)", 0.0, 20.0, 5.3 if kind == "신용대출" else 4.0, step=0.1, format="%.2f")
    rate_type = c3.radio("금리 유형", ["변동", "고정"], horizontal=True)
    c1, c2, c3 = st.columns(3)
    start = c1.date_input("대출 받은 날 (최초 실행일)", date(2025, 3, 1), min_value=date(2005, 1, 1), max_value=date.today(),
                          help="중도상환수수료는 최초 실행일부터 3년 동안만 붙습니다.")
    remain = c2.number_input("남은 기간 (개월)", 1, 480, {"신용대출": 24, "전세대출": 18}.get(kind, 300),
                             help="신용대출을 1년마다 연장한다면, 앞으로 갚을 때까지 예상 기간을 넣으세요.")
    elapsed = max((date.today().year - start.year) * 12 + date.today().month - start.month, 0)
    term_m = elapsed + remain
    c3.metric("경과 기간", f"{elapsed}개월", "수수료 면제" if elapsed >= PF["exempt_months"] else f"면제까지 {PF['exempt_months'] - elapsed}개월",
              delta_color="off")

    key = f"{'주택담보대출' if kind != '신용대출' else '신용대출'}_{rate_type}"
    after = start >= date.fromisoformat(PF["effective"])
    default_fee = (PF["avg_rates_after"] if after else PF["avg_rates_before"])[key]
    c1, c2 = st.columns(2)
    fee_rate = c1.number_input("중도상환수수료율 (%)", 0.0, 3.0, float(default_fee), step=0.05, format="%.2f",
                               help=f"{'2025.1.13 이후' if after else '2025.1.13 이전'} 계약 은행권 평균값을 기본으로 넣었습니다. 약정서의 실제 요율로 바꾸세요.")
    extra = c2.number_input("기타 비용 (만 원)", 0, 1000, 0 if kind == "신용대출" else 50, step=5,
                            help="인지세, 근저당 설정·말소 비용, 보증료 등. 주택담보대출은 수십만 원이 들 수 있습니다.") * 1e4


res = fc.refinance(balance, cur_rate, new_rate, remain, method, elapsed, term_m, fee_rate, extra, PF["exempt_months"])
if "refi_logged" not in st.session_state or st.session_state["refi_logged"] != (kind, res.net_saving > 0):
    st.session_state["refi_logged"] = (kind, res.net_saving > 0)
    cm.track("refi_calc", kind=kind, positive=bool(res.net_saving > 0), rate_gap=round(cur_rate - new_rate, 2))

k = st.columns(4)
k[0].metric("월 상환액", cm.krw(res.new_monthly), cm.krw(res.new_monthly - res.cur_monthly, signed=True), delta_color="inverse")
k[1].metric("이자 절약 (남은 기간)", cm.krw(res.interest_saving))
k[2].metric("중도상환수수료 + 비용", cm.krw(res.fee + res.extra_cost),
            "면제 구간" if res.fee == 0 else f"{max(PF['exempt_months'] - elapsed, 0)}개월 뒤 면제", delta_color="off")
k[3].metric("최종 이득", cm.krw(res.net_saving, signed=True))

if res.net_saving > 0:
    be = f"**{res.breakeven_month}개월**이면 비용을 회수합니다." if res.breakeven_month else ""
    st.success(f"갈아타면 남은 기간 동안 **{cm.krw(res.net_saving)}** 이득입니다. {be}")
elif cur_rate <= new_rate:
    st.info("새 금리가 지금보다 높거나 같아 갈아탈 이유가 없습니다.")
else:
    wait = max(PF["exempt_months"] - elapsed, 0)
    st.warning(f"금리는 낮아지지만 수수료·비용이 더 커서 지금은 손해입니다."
               + (f" 중도상환수수료가 사라지는 **{wait}개월 뒤**에 다시 계산해 보세요." if wait and res.fee > 0 else ""))

# 누적 순이득 곡선
st.subheader("갈아탄 뒤 누적 이득")
cum = pd.DataFrame({"개월": range(1, len(res.cumulative) + 1), "누적 이득(만 원)": [c / 1e4 for c in res.cumulative]})
line = alt.Chart(cum).mark_area(line={"color": "#1F7A73"}, color=alt.Gradient(
    gradient="linear", stops=[alt.GradientStop(color="#E3F1EE", offset=0), alt.GradientStop(color="#8FB8B2", offset=1)],
    x1=1, x2=1, y1=1, y2=0)).encode(
    x=alt.X("개월:Q"), y=alt.Y("누적 이득(만 원):Q"),
    tooltip=["개월", alt.Tooltip("누적 이득(만 원):Q", format=",.0f")])
zero = alt.Chart(pd.DataFrame({"누적 이득(만 원)": [0]})).mark_rule(color="#E4572E", strokeDash=[4, 3]).encode(y="누적 이득(만 원):Q")
st.altair_chart((line + zero).properties(height=240), width="stretch")
st.caption("처음에는 수수료·비용 때문에 마이너스에서 출발하고, 매달 줄어든 상환액만큼 올라갑니다. 0선을 넘는 지점이 본전입니다.")

# 금리 차이별 민감도
st.subheader("금리를 얼마나 낮춰야 이득일까")
rows = []
for gap in [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]:
    r = fc.refinance(balance, cur_rate, max(cur_rate - gap, 0), remain, method, elapsed, term_m, fee_rate, extra, PF["exempt_months"])
    rows.append({"금리 인하폭": f"−{gap:.2f}%p", "새 금리": f"{max(cur_rate - gap, 0):.2f}%", "최종 이득": cm.krw(r.net_saving, signed=True),
                 "본전 회수": f"{r.breakeven_month}개월" if r.breakeven_month else "회수 못 함"})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

with st.expander("✅ 갈아타기 전에 확인할 것"):
    st.markdown(
        f"- **비교는 앱으로**: {R['refinance_platform']['note']}\n"
        "- **조회만으로는 신용점수가 떨어지지 않습니다.** 여러 곳을 비교해도 괜찮습니다.\n"
        f"- **수수료 면제 시점**: 대출 후 {PF['exempt_months'] // 12}년이 지나면 보통 중도상환수수료가 없습니다. 곧 면제라면 기다렸다가 갈아타는 게 나을 수 있습니다.\n"
        "- **주택담보대출은 한도도 다시 계산**됩니다. 스트레스 DSR 강화로 갈아탈 때 한도가 줄 수 있으니 '주택담보대출 한도 계산기'로 먼저 확인하세요.\n"
        "- 새 금리가 변동금리라면 앞으로 기준금리가 오르면 상환액도 오릅니다. "
        f"(현재 기준금리 연 {R['base_rate']['value']}%, {R['base_rate']['note']})"
    )
cm.rule_sources("prepayment_fee", "중도상환수수료 개편 근거")
cm.v3_disclaimer()
cm.sidebar_note_v3()

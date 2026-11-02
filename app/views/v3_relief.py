"""v3 · 서민금융·채무조정 길잡이: 정책 대출 자격과 연체 단계별 도움 창구."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("v3_relief")
R = cm.load_rules()
PL, DR = R["policy_loans"], R["debt_relief"]
fc = cm.fc

st.title("🤝 서민금융·채무조정 길잡이")
st.caption("2026년 1월 햇살론이 통합되고 금리 상한이 15.9%에서 **12.5%로** 낮아졌습니다. 내 조건으로 쓸 수 있는 정책 대출과, "
           "빚이 밀렸을 때 단계별로 찾아갈 곳을 정리했습니다.")

tab1, tab2, tab3 = st.tabs(["💳 정책 대출 자격 확인", "🧯 연체·빚 정리 도움", "🚨 불법 대출 피하기"])

with tab1:
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        age = c1.number_input("만 나이", 19, 100, 29)
        income = c2.number_input("연소득 (만 원)", 0, 20000, 3200, step=100)
        bureau = c3.radio("신용평가사", ["KCB", "NICE"], horizontal=True, help="토스·카카오뱅크 등은 KCB, 네이버페이 등은 NICE 점수를 보여줍니다.")
        c1, c2, c3 = st.columns(3)
        score = c1.number_input("신용점수 (모르면 0)", 0, 1000, 0, step=10)
        vul = c2.toggle("사회적배려대상자", help=", ".join(PL["vulnerable_groups"]))
        overdue = c3.toggle("현재 연체 중")
    matches = fc.policy_loan_matches(R, age, income, score or None, bureau, vul, overdue)
    if st.session_state.get("relief_n") != len(matches):
        st.session_state["relief_n"] = len(matches)
        cm.track("relief_check", n_match=len(matches))

    cut = PL["low_score_cutoff"][bureau]
    if not score:
        st.caption(f"신용점수를 넣으면 '하위 20%' 조건까지 확인합니다. 기준선은 {bureau} 약 {cut}점 안팎으로 알려져 있습니다.")
    if matches:
        st.success(f"조건상 신청해 볼 수 있는 상품 **{len(matches)}개**")
        for m in matches:
            with st.container(border=True):
                a, b, c = st.columns([2, 1, 1])
                a.markdown(f"**{m['name']}**  \n<small>{m['why']}</small>", unsafe_allow_html=True)
                b.metric("금리", m["rate"])
                c.metric("한도", m["limit"])
                st.caption(m["desc"])
        st.markdown(f"👉 신청·상담: [{PL['apply']['title']}]({PL['apply']['url']}) · 은행·저축은행 앱의 햇살론 메뉴")
    else:
        st.info("입력한 조건으로는 햇살론 대상이 아닐 가능성이 큽니다. 일반 은행 대출과 '대출 갈아타기 계산기'를 먼저 비교해 보세요.")
    if vul:
        st.caption("사회적배려대상자는 대출 약정 **전에** 증명서류를 내야 우대가 적용됩니다(약정 후 소급 불가).")
    cm.rule_sources("policy_loans", "햇살론 개편 근거")

with tab2:
    STAGES = ["아직 연체는 없지만 곧 갚기 어려울 것 같다", "연체 30일 이하", "연체 31~89일", "연체 90일 이상",
              "7년 이상 오래된 빚(5,000만 원 이하)이 남아 있다"]
    stage = st.radio("지금 상황에 가장 가까운 것은?", STAGES)
    guide = {
        0: ("신용회복위원회 · 신속채무조정", "연체 전이나 연체 30일 이하라도 상환이 어려우면 상환기간 연장·이자 조정을 신청할 수 있습니다. 연체 기록이 쌓이기 전에 움직이는 것이 가장 유리합니다."),
        1: ("신용회복위원회 · 신속채무조정", "연체 30일 이하 단계의 채무조정입니다. 신용점수 하락과 연체 정보 등록을 최소화할 수 있습니다."),
        2: ("신용회복위원회 · 프리워크아웃", "연체 31~89일 단계에서 이자율 인하·상환기간 연장을 지원합니다."),
        3: ("신용회복위원회 · 개인워크아웃 / 법원 개인회생·파산", "연체 90일 이상이면 원금 일부 감면까지 가능한 개인워크아웃, 또는 법원 절차(개인회생·파산)를 검토합니다. 대한법률구조공단(132)에서 비용 지원 상담이 가능합니다."),
        4: ("새도약기금", DR["새도약기금"]["target"] + ". " + DR["새도약기금"]["status"]),
    }
    i = STAGES.index(stage)
    title, body = guide[i]
    with st.container(border=True):
        st.markdown(f"### 👉 {title}")
        st.write(body)
        if i < 4:
            st.markdown(f"**연락처**: 신용회복위원회 {DR['신용회복위원회']['contact']} · [홈페이지]({DR['신용회복위원회']['url']})")
        else:
            st.markdown(f"**조회**: {DR['새도약기금']['contact']} · [새도약기금]({DR['새도약기금']['url']})  \n"
                        "소각 대상자에게는 문자로 개별 안내됩니다. 안내 문자를 사칭한 스미싱에 주의하고, 링크 대신 공식 홈페이지에서 직접 조회하세요.")
    st.markdown("**함께 알아둘 것**")
    st.markdown(
        f"- **신용사면**: {DR['신용사면']['rule']}. {DR['신용사면']['status']}\n"
        "- **무료 상담**: 서민금융콜센터 **1397** (정책 대출·채무조정 통합 상담), 금융감독원 **1332**\n"
        "- 채무조정 중에도 생계비 통장, 최저생계비 이하 급여 등은 압류가 제한됩니다. 압류 문제는 법률구조공단(132)에 문의하세요."
    )
    st.caption("앱의 '신용사면 시뮬레이터'에서는 연체 기록 삭제가 대출 시장 전체에 어떤 영향을 주는지 분석해 볼 수 있습니다.")
    cm.rule_sources("debt_relief", "채무조정 제도 근거")

with tab3:
    mx = R["max_legal_rate"]["value"]
    st.markdown(f"#### 법정 최고금리는 연 {mx:.0f}%입니다")
    c1, c2 = st.columns(2)
    principal = c1.number_input("빌린 돈 (만 원)", 10, 10000, 100, step=10)
    weekly = c2.number_input("갚기로 한 총액 (만 원)", 10, 20000, 130, step=10)
    weeks = st.slider("상환 기간 (주)", 1, 52, 4)
    years = weeks / 52
    apr = ((weekly / principal) - 1) / years * 100 if years else 0
    if apr > mx:
        st.error(f"이 조건의 연이자율은 약 **{apr:,.0f}%로** 법정 최고금리 {mx:.0f}%를 넘습니다. **불법 대출**입니다. "
                 "최고금리를 넘는 이자는 갚을 의무가 없습니다.")
    else:
        st.success(f"연이자율 약 {apr:.1f}%로 최고금리 이내입니다. 그래도 등록된 금융회사인지 꼭 확인하세요.")
    st.markdown(
        f"- 급전이 필요하면 불법사금융 대신 **불법사금융예방대출**(연 {PL['불법사금융예방대출']['rate']}%, 전액 상환 시 실질 "
        f"{PL['불법사금융예방대출']['effective_rate_full_repay']}%)을 먼저 알아보세요. 서민금융콜센터 1397.\n"
        "- 불법 추심·고금리 피해 신고: 금융감독원 **1332**, 경찰 **112**\n"
        "- 등록 대부업체 여부는 금융감독원 '파인(fine.fss.or.kr)'에서 조회할 수 있습니다."
    )
    cm.rule_sources("max_legal_rate", "최고금리 근거")
cm.v3_disclaimer()
cm.sidebar_note_v3()

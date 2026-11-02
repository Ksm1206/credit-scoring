"""v3 · 내 금융 혜택 찾기: 1분 진단으로 바뀐 제도 중 나에게 해당하는 것을 '아낄 수 있는 돈' 순으로."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("v3_benefits")
R = cm.load_rules()
fc = cm.fc

st.title("💡 내 금융 혜택 찾기")
st.caption(f"최근 1~2년 사이 대출 제도가 많이 바뀌었습니다(햇살론 통합, 중도상환수수료 인하, 금리인하요구 자동 신청, 스트레스 DSR, 10·15 대책 등). "
           f"1분 진단으로 **나에게 해당하는 것만, 아낄 수 있는 돈 순서로** 알려드려요. 입력값은 저장되지 않습니다. (기준일 {R['as_of']})")

with st.form("diag"):
    st.markdown("**① 기본 정보**")
    c1, c2, c3, c4 = st.columns(4)
    age = c1.number_input("만 나이", 19, 100, 31)
    income = c2.number_input("연소득 (만 원)", 0, 100000, 4200, step=100)
    bureau = c3.selectbox("신용평가사", ["KCB", "NICE"])
    score = c4.number_input("신용점수 (모르면 0)", 0, 1000, 0, step=10)

    st.markdown("**② 가장 큰 대출 1개**")
    c1, c2, c3, c4 = st.columns(4)
    kind = c1.selectbox("종류", ["없음", "신용대출", "주택담보대출", "전세대출"], index=1)
    bal = c2.number_input("남은 원금 (만 원)", 0, 200000, 3000, step=100)
    rate = c3.number_input("금리 (연 %)", 0.0, 30.0, 7.2, step=0.1, format="%.2f")
    start = c4.date_input("대출 받은 날", date(2024, 9, 1), min_value=date(2005, 1, 1), max_value=date.today())
    c1, c2 = st.columns(2)
    remain = c1.number_input("남은 기간 (개월)", 1, 480, 24)
    method = c2.selectbox("상환 방식", fc.METHODS, index=0)

    st.markdown("**③ 대출 받은 뒤 생긴 변화** (해당하는 것 모두)")
    cols = st.columns(3)
    triggers = [t for i, t in enumerate(R["rate_cut_right"]["triggers"]) if cols[i % 3].checkbox(t, key=f"b_{i}")]

    st.markdown("**④ 그 밖의 상황**")
    c1, c2, c3 = st.columns(3)
    overdue = c1.selectbox("연체 상태", ["없음", "곧 어려울 것 같음", "30일 이하", "31~89일", "90일 이상", "7년 이상 장기연체"])
    vul = c2.toggle("사회적배려대상자", help=", ".join(R["policy_loans"]["vulnerable_groups"]))
    house = c3.toggle("1~2년 안에 집 살 계획")
    go = st.form_submit_button("내 혜택 찾기", type="primary", width="stretch")

if go:
    st.session_state["diag_done"] = True
if not st.session_state.get("diag_done"):
    st.info("정보를 입력하고 **내 혜택 찾기**를 눌러 주세요.")
    cm.v3_disclaimer()
    st.stop()

# ---------------------------------------------------------------- 혜택 계산
elapsed = max((date.today().year - start.year) * 12 + date.today().month - start.month, 0)
has_loan = kind != "없음" and bal > 0
won = bal * 1e4
cards = []  # (연간 효과 원, 제목, 이유, 할 일, 이동할 화면)

if has_loan and rate > R["max_legal_rate"]["value"]:
    cards.append((10 ** 12, "🚨 법정 최고금리 초과", f"금리 {rate}%는 법정 최고금리 연 {R['max_legal_rate']['value']:.0f}%를 넘습니다.",
                  "최고금리를 넘는 이자는 갚을 의무가 없습니다. 금융감독원 1332에 상담·신고하세요.", "v3_relief"))

if has_loan and triggers:
    sv = fc.rate_cut_saving(won, rate, 0.3, remain, method)
    cards.append((sv["first_year"], "📉 금리인하요구권 신청",
                  f"'{triggers[0]}'{' 외 ' + str(len(triggers) - 1) + '가지' if len(triggers) > 1 else ''} 변화가 있어 신청 사유가 됩니다.",
                  f"0.3%p만 낮아져도 첫 1년 **{cm.krw(sv['first_year'])}** 절약. 은행 앱에서 신청하거나 마이데이터 앱의 자동 신청을 켜세요. "
                  f"(은행권 평균 수용률 {R['rate_cut_right']['acceptance_rate_banks']}%, 신청은 무료)", "v3_rate_cut"))

if has_loan and kind in ("신용대출", "주택담보대출", "전세대출"):
    pf = R["prepayment_fee"]
    key = f"{'주택담보대출' if kind != '신용대출' else '신용대출'}_변동"
    fee_rate = (pf["avg_rates_after"] if start >= date.fromisoformat(pf["effective"]) else pf["avg_rates_before"])[key]
    term_guess = max(elapsed + remain, 1)
    target = max(rate - 1.0, 0.5)
    r = fc.refinance(won, rate, target, remain, method, elapsed, term_guess, fee_rate, 0 if kind == "신용대출" else 5e5)
    yearly = r.net_saving / max(remain / 12, 1)
    exempt = elapsed >= pf["exempt_months"]
    why = ("대출 후 3년이 지나 **중도상환수수료가 없는** 구간입니다." if exempt else
           f"중도상환수수료는 약 {cm.krw(r.fee)}(요율 {fee_rate}%)이고 {pf['exempt_months'] - elapsed}개월 뒤 면제됩니다.")
    if r.net_saving > 0:
        cards.append((yearly, "🔄 더 낮은 금리로 갈아타기", why,
                      f"1%p 낮은 {target:.1f}%로 갈아타면 수수료·비용을 빼고 남은 기간 **{cm.krw(r.net_saving)}** 이득"
                      f"{f'(본전 {r.breakeven_month}개월)' if r.breakeven_month else ''}. 대출비교 앱에서 실제 금리를 조회해 보세요.", "v3_refinance"))

low = score and score <= R["policy_loans"]["low_score_cutoff"][bureau]
matches = fc.policy_loan_matches(R, age, income, score or None, bureau, vul, overdue != "없음")
hs = [m for m in matches if m["name"].startswith("햇살론") and m["name"] != "햇살론유스"]
if hs and (not has_loan or rate > 12.5):
    gain = won * (rate - 12.5) / 100 if has_loan and kind == "신용대출" else 0
    cards.append((gain, f"💳 {hs[0]['name']} 대상 가능성",
                  f"{hs[0]['why']} 조건에 해당합니다. 2026년 1월부터 금리 상한이 15.9%에서 **12.5%로** 낮아졌습니다.",
                  (f"지금 {rate}% 신용대출을 12.5% 이하로 바꾸면 연 약 **{cm.krw(gain)}** 절약. " if gain > 0 else "") +
                  f"한도 {hs[0]['limit']}. 서민금융진흥원(1397)에서 확인하세요.", "v3_relief"))
if any(m["name"] == "햇살론유스" for m in matches):
    cards.append((0, "🎓 햇살론유스 (청년)", "만 19~34세, 연소득 3,500만 원 이하라 청년 전용 정책 대출(연 1.9~4%, 최대 1,200만 원)을 알아볼 수 있습니다.",
                  "대학생·취업준비생·사회초년생 대상. 세부 요건은 서민금융진흥원에서 확인하세요.", "v3_relief"))

if overdue != "없음":
    where = {"곧 어려울 것 같음": "신용회복위원회 신속채무조정", "30일 이하": "신용회복위원회 신속채무조정",
             "31~89일": "신용회복위원회 프리워크아웃", "90일 이상": "신용회복위원회 개인워크아웃 또는 개인회생",
             "7년 이상 장기연체": "새도약기금 (소각·채무조정 대상 조회)"}[overdue]
    cards.append((10 ** 11, "🧯 연체·빚 정리 도움", f"'{overdue}' 단계에서는 **{where}를** 이용할 수 있습니다.",
                  "빨리 움직일수록 이자 감면 폭이 크고 신용 회복이 빠릅니다. 서민금융콜센터 1397에서 무료 통합 상담.", "v3_relief"))

if house:
    cards.append((0, "🏠 집 사기 전 대출 한도 확인", "6·27, 10·15 대책과 스트레스 DSR로 수도권 주택담보대출 한도가 크게 줄었습니다.",
                  "서울·규제지역은 무주택 LTV 40%(생애최초 70%), 집값 15억 이하도 최대 6억, 스트레스 금리 3% 적용. "
                  "계획한 집값으로 실제 한도부터 계산해 보세요.", "v3_mortgage"))

if score and not low:
    cards.append((0, "📊 신용점수 관리", f"현재 {bureau} {score}점. 카드 한도 사용률을 낮추고 연체를 피하면 점수가 오르고, 그 자체가 금리인하요구 사유가 됩니다.",
                  "'내 신용점수' 화면에서 내 조건의 감점 사유와 점수 올리는 방법을 확인하세요.", "my_score"))

cards.sort(key=lambda c: -c[0])
if st.session_state.get("diag_logged") != len(cards):
    st.session_state["diag_logged"] = len(cards)
    cm.track("benefit_check", n_cards=len(cards), has_loan=has_loan, n_triggers=len(triggers))

# ---------------------------------------------------------------- 결과
money = [c[0] for c in cards if 0 < c[0] < 10 ** 10]
st.divider()
k = st.columns(3)
k[0].metric("나에게 해당하는 항목", f"{len(cards)}개")
k[1].metric("연간 아낄 수 있는 돈 (추정)", cm.krw(sum(money)) if money else "-",
            help="금리인하 0.3%p, 갈아타기 1%p 인하 등 보수적 가정. 실제 금액은 심사 결과에 따라 다릅니다.")
k[2].metric("기준금리", f"연 {R['base_rate']['value']}%", "11월 26일 결정 예정", delta_color="off")

PAGES = {"v3_refinance": "대출 갈아타기 계산기", "v3_rate_cut": "금리인하요구권 진단", "v3_mortgage": "주택담보대출 한도 계산기",
         "v3_relief": "서민금융·채무조정 길잡이", "my_score": "내 신용점수"}
if not cards:
    st.success("지금 바로 챙길 혜택은 보이지 않습니다. 대출 금리가 시장보다 높은지 '대출 갈아타기 계산기'로 한 번 확인해 보세요.")
for amt, title, why, todo, page in cards:
    with st.container(border=True):
        a, b = st.columns([4, 1])
        a.markdown(f"#### {title}")
        if 0 < amt < 10 ** 10:
            b.metric("연간 효과", cm.krw(amt))
        st.markdown(why.replace("~", "\\~"))   # '19~34세 … 1.9~4%'의 물결표 두 개가 취소선으로 바뀌지 않게
        st.markdown(f"**할 일** · {todo}".replace("~", "\\~"))
        st.page_link(str(Path(__file__).with_name(f"{page}.py")), label=f"{PAGES[page]}에서 자세히 보기 →")
cm.v3_disclaimer()
cm.sidebar_note_v3()

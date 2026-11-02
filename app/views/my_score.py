"""① 내 신용점수: 점수 계산, 거절 사유 설명(AI 기본법), 개선 방법, A/B 실험."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

CARD = cm.load_card()
UID, SID, VARIANT = cm.identify()
cm.page_view("my_score")

ACTIONABLE = {
    "rev_util": "리볼빙(카드 한도) 사용률을 {target} 이하로 낮추면",
    "late_30_59": "앞으로 2년간 30일 이상 연체가 없으면",
    "late_60_89": "앞으로 2년간 60일 이상 연체가 없으면",
    "late_90": "90일 이상 연체 기록이 정리되면",
}
REASONS = {  # 거절·감점 사유 안내 문구 (이용자 설명용)
    "rev_util": "카드·리볼빙 한도 대비 사용액 비중이 높습니다.",
    "late_30_59": "최근 2년 안에 30~59일 연체 기록이 있습니다.",
    "late_60_89": "최근 2년 안에 60~89일 연체 기록이 있습니다.",
    "late_90": "90일 이상 장기 연체 기록이 있습니다.",
    "age": "같은 연령대의 평균 부도율이 상대적으로 높습니다. (연령 반영의 공정성은 '청년 공정성' 화면에서 점검합니다)",
    "monthly_income": "소득 수준 또는 소득 미기재가 감점 요인입니다.",
    "debt_ratio": "소득 대비 부채상환 부담(DTI)이 높습니다.",
    "real_estate_loans": "부동산 담보대출 보유 구성이 감점 요인입니다.",
    "dependents": "부양가족 수가 감점 요인입니다.",
}


def improvement_tips(detail):
    tips = []
    for f, msg in ACTIONABLE.items():
        spec = CARD["features"].get(f)
        if not spec:
            continue
        best_bin = max(spec["points"], key=spec["points"].get)
        gain = spec["points"][best_bin] - detail[f]["points"]
        if gain > 0:
            target = f"{float(best_bin.split(',')[1].strip(' ]')) * 100:.0f}%" if f == "rev_util" else ""
            tips.append((gain, msg.format(target=target)))
    return sorted(tips, reverse=True)[:3]


def reason_codes(detail, k=3):
    """항목별 '최고 구간 대비 잃은 점수'가 큰 순서 = 주요 감점 사유."""
    lost = []
    for f, d in detail.items():
        best = max(CARD["features"][f]["points"].values())
        if best - d["points"] > 0:
            lost.append((best - d["points"], f))
    return sorted(lost, reverse=True)[:k]


def percentile(score):
    t = cm.score_table()
    n = t[["good", "bad"]].sum().sum()
    above = t.loc[t.score > score, ["good", "bad"]].sum().sum()
    return above / n


# ------------------------------------------------------------ 화면
st.title("📊 내 신용점수")
st.caption("대출 15만 건으로 학습한 스코어카드로 내 조건의 예상 점수, 감점 사유, 점수 올리는 방법을 알려드려요. "
           "입력값은 저장되지 않습니다.")

with st.form("calc"):
    c1, c2 = st.columns(2)
    age = c1.number_input("나이", 19, 100, 30)
    dependents = c2.number_input("부양가족 수", 0, 10, 0)
    income_known = c1.checkbox("월소득 입력", value=True)
    income_man = c2.number_input("월 세후소득 (만원)", 0, 10000, 300, step=10, disabled=not income_known)
    rev_util = st.slider("카드 한도 대비 사용률 (%)", 0, 150, 30,
                         help="리볼빙·카드 사용액 ÷ 총 한도. 한도를 넘겨 쓰면 100% 초과")
    debt_ratio = st.slider("월 부채상환액 ÷ 월소득 (DTI, %)", 0, 150, 30)
    real_estate = st.number_input("주택담보대출 건수", 0, 10, 0)
    st.markdown("**최근 2년 연체 이력**")
    l1, l2, l3 = st.columns(3)
    late_30 = l1.number_input("30~59일", 0, 20, 0)
    late_60 = l2.number_input("60~89일", 0, 20, 0)
    late_90 = l3.number_input("90일 이상", 0, 20, 0)
    submitted = st.form_submit_button("점수 계산하기", type="primary", width="stretch")

if submitted:
    values = {
        "age": age, "dependents": dependents, "rev_util": rev_util / 100, "debt_ratio": debt_ratio / 100,
        "monthly_income": income_man * 10000 / cm.KRW_PER_USD if income_known else float("nan"),
        "real_estate_loans": real_estate, "late_30_59": late_30, "late_60_89": late_60, "late_90": late_90,
    }
    score, detail = cm.sc.score_one(CARD, values)
    st.session_state["n_calc"] = st.session_state.get("n_calc", 0) + 1
    st.session_state["result"] = {"score": score, "detail": detail, "calc_id": uuid.uuid4().hex[:8],
                                  "feedback": None, "late_any": bool(late_30 or late_60 or late_90)}
    g = cm.grade_of(score)
    cm.track("calc_submit", score=score, grade=g["grade"], n_calc=st.session_state["n_calc"],
             bins={f: d["bin"] for f, d in detail.items()})

res = st.session_state.get("result")
if res:
    score, detail = res["score"], res["detail"]
    g = cm.grade_of(score)
    label, kind = cm.decision_of(score)
    pd_est = float(cm.sc.score_to_pd([score], CARD["scaling"])[0])

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("내 점수", f"{score}점")
    m2.metric("등급", f"{g['grade']} ({g['desc']})")
    m3.metric("예상 부도확률", f"{pd_est:.1%}")
    top = percentile(score)
    m4.metric("전체 중 위치", f"상위 {max(top, 0.01) * 100:.0f}%" if top <= 0.5 else f"하위 {(1 - top) * 100:.0f}%")
    getattr(st, kind)(f"{label}  ·  같은 등급의 실제 부도율 {g['bad_rate']:.1%}")

    if not res.get("viewed"):
        res["viewed"] = True
        cm.track("result_view", score=score, grade=g["grade"], calc_id=res["calc_id"])

    tips = improvement_tips(detail)
    contrib = pd.DataFrame([{"항목": CARD["features"][f]["label_ko"],
                             "평균 대비": d["points"] - CARD["features"][f]["default_points"]}
                            for f, d in detail.items()]).sort_values("평균 대비")

    def show_tips():
        if tips:
            for gain, msg in tips:
                st.info(f"**{msg} +{gain}점**  → 예상 {score + gain}점")
        else:
            st.success("개선할 수 있는 항목이 거의 없어요. 지금 상태를 유지하세요!")

    if VARIANT == "B":   # 코칭형: 개선 방법을 먼저 보여준다
        st.subheader("🚀 점수 올리는 방법")
        show_tips()
        with st.expander("항목별 점수 보기"):
            st.bar_chart(contrib.set_index("항목")["평균 대비"], horizontal=True)
    else:                # 기본형: 항목별 점수 중심
        st.subheader("항목별 점수")
        st.bar_chart(contrib.set_index("항목")["평균 대비"], horizontal=True)
        st.caption("0 = 평균 수준. 음수인 항목이 점수를 깎고 있어요.")
        if st.button("점수 올리는 방법 보기"):
            res["tips_open"] = True
            cm.track("tip_open", score=score, calc_id=res["calc_id"])
        if res.get("tips_open"):
            show_tips()

    # ---------------- AI 기본법: 설명 가능성 + 사람의 개입 요청
    with st.expander("📄 점수 산정 설명서 (주요 감점 사유)", expanded=score < cm.load_policy()["approve_cutoff"]):
        codes = reason_codes(detail)
        if codes:
            for i, (lost, f) in enumerate(codes, 1):
                st.markdown(f"**{i}. {CARD['features'][f]['label_ko']}** (−{lost}점)  \n{REASONS[f]}")
        else:
            st.markdown("모든 항목이 최고 구간입니다.")
        st.caption("이 점수는 9개 항목의 구간 점수를 더한 값입니다. 각 항목의 구간과 점수는 '모델 카드' 화면에서 모두 공개합니다.")
        if not res.get("review_requested"):
            if st.button("🙋 사람 심사 요청하기", help="자동 판정에 이의가 있을 때 사람이 다시 검토하도록 요청합니다(시연용)."):
                res["review_requested"] = True
                cm.track("human_review_request", score=score, grade=g["grade"], calc_id=res["calc_id"])
                st.rerun()
        else:
            st.success("사람 심사 요청이 접수되었습니다. (시연용: 실제 심사로 이어지지 않습니다)")

    if res.get("late_any"):
        st.info("연체 기록이 있으시네요. 정부의 **신용사면**(연체 기록 삭제)처럼 기록이 지워지면 점수가 어떻게 변하는지, "
                "그게 은행과 다른 대출자에게 어떤 영향을 주는지는 '신용사면 시뮬레이터'에서 볼 수 있어요.")

    st.divider()
    if res["feedback"] is None:
        st.write("이 결과가 도움이 되었나요?")
        f1, f2, _ = st.columns([1, 1, 3])
        if f1.button("👍 도움됐어요"):
            res["feedback"] = True
        if f2.button("👎 아쉬워요"):
            res["feedback"] = False
        if res["feedback"] is not None:
            cm.track("feedback", helpful=res["feedback"], score=score, calc_id=res["calc_id"])
            st.rerun()
    else:
        st.write("피드백 감사합니다! 🙏")

    if st.button("🔗 친구에게 공유하기"):
        cm.track("share_click", score_band=g["grade"])
        try:  # 배포 주소를 직접 읽어 공유 링크를 만든다 (uid는 빼서 친구가 새 사용자로 잡히게)
            base = (st.context.url or "").split("?")[0]
        except Exception:
            base = ""
        st.code(f"{base or 'https://credit-score-ksm.streamlit.app/'}?ref=share", language=None)

with st.expander("ℹ️ 이 시뮬레이터에 대해"):
    st.markdown(
        f"- {cm.source_link('data')} 데이터(미국 대출자 15만 명)로 만든 **학습용 모델**이며, 실제 신용평가사(KCB·NICE) 점수와는 다릅니다.\n"
        "- 소득은 1달러 = 1,400원으로 환산합니다.\n"
        "- 서비스 개선을 위해 점수·등급과 버튼 클릭만 익명으로 기록하며, 입력하신 숫자 원본은 저장하지 않습니다."
    )

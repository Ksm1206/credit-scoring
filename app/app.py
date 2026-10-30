"""신용점수 시뮬레이터 (Streamlit).

실행: streamlit run app/app.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scorecard as sc  # noqa: E402
import events  # noqa: E402

KRW_PER_USD = 1400  # 학습 데이터(미국)가 달러 기준이라 고정 환율로 환산

st.set_page_config(page_title="내 신용점수 시뮬레이터", page_icon="📊", layout="centered")


@st.cache_resource
def load_models():
    card = json.loads((ROOT / "models/scorecard.json").read_text())
    policy = json.loads((ROOT / "models/policy.json").read_text())
    return card, policy


CARD, POLICY = load_models()


# ------------------------------------------------------------ 사용자·실험군
def identify():
    qp = st.query_params
    if "uid" not in qp:  # URL에 익명 ID를 남겨 재방문(리텐션)을 추적
        qp["uid"] = uuid.uuid4().hex[:12]
    ss = st.session_state
    ss.setdefault("session_id", uuid.uuid4().hex)
    uid = qp["uid"]
    # 같은 사용자는 항상 같은 실험군 (해시 기반 50:50)
    variant = "A" if int(hashlib.md5(uid.encode()).hexdigest(), 16) % 2 == 0 else "B"
    return uid, ss["session_id"], variant


UID, SID, VARIANT = identify()


def track(event, **props):
    events.log(event, user_id=UID, session_id=SID, variant=VARIANT, props=props)


if not st.session_state.get("viewed"):
    st.session_state["viewed"] = True
    track("page_view", ref=st.query_params.get("ref", "direct"))


# ------------------------------------------------------------ 점수 계산 로직
def grade_of(score):
    for g in POLICY["grades"]:
        if score >= g["min"]:
            return g
    return POLICY["grades"][-1]


def decision_of(score):
    if score >= POLICY["approve_cutoff"]:
        return "✅ 승인 예상", "success"
    if score >= POLICY["review_cutoff"]:
        return "🟡 추가 심사 예상", "warning"
    return "⛔ 거절 예상", "error"


ACTIONABLE = {
    "rev_util": "리볼빙(카드 한도) 사용률을 {target} 이하로 낮추면",
    "late_30_59": "앞으로 2년간 30일 이상 연체가 없으면",
    "late_60_89": "앞으로 2년간 60일 이상 연체가 없으면",
    "late_90": "90일 이상 연체 기록이 정리되면",
}


def improvement_tips(values, detail):
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


# ------------------------------------------------------------ 화면
st.title("📊 내 신용점수 시뮬레이터")
st.caption("실제 대출 15만 건으로 학습한 스코어카드 모델로, 내 조건의 예상 점수와 점수를 올리는 방법을 알려드려요. "
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
    submitted = st.form_submit_button("점수 계산하기", type="primary", use_container_width=True)

if submitted:
    values = {
        "age": age, "dependents": dependents, "rev_util": rev_util / 100, "debt_ratio": debt_ratio / 100,
        "monthly_income": income_man * 10000 / KRW_PER_USD if income_known else float("nan"),
        "real_estate_loans": real_estate, "late_30_59": late_30, "late_60_89": late_60, "late_90": late_90,
        "open_credit_lines": 0,
    }
    score, detail = sc.score_one(CARD, values)
    st.session_state["n_calc"] = st.session_state.get("n_calc", 0) + 1
    st.session_state["result"] = {"values": values, "score": score, "detail": detail,
                                  "calc_id": uuid.uuid4().hex[:8], "feedback": None}
    g = grade_of(score)
    track("calc_submit", score=score, grade=g["grade"], n_calc=st.session_state["n_calc"],
          bins={f: d["bin"] for f, d in detail.items()})

res = st.session_state.get("result")
if res:
    score, detail, values = res["score"], res["detail"], res["values"]
    g = grade_of(score)
    label, kind = decision_of(score)
    pd_est = float(sc.score_to_pd([score], CARD["scaling"])[0])

    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("내 점수", f"{score}점")
    m2.metric("등급", f"{g['grade']} ({g['desc']})")
    m3.metric("예상 부도확률", f"{pd_est:.1%}")
    getattr(st, kind)(f"{label}  ·  같은 등급의 실제 부도율 {g['bad_rate']:.1%}")

    if not res.get("viewed"):
        res["viewed"] = True
        track("result_view", score=score, grade=g["grade"], calc_id=res["calc_id"])

    tips = improvement_tips(values, detail)
    contrib = pd.DataFrame([{"항목": CARD["features"][f]["label_ko"], "점수": d["points"],
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
            track("tip_open", score=score, calc_id=res["calc_id"])
        if res.get("tips_open"):
            show_tips()

    st.divider()
    if res["feedback"] is None:
        st.write("이 결과가 도움이 되었나요?")
        f1, f2, _ = st.columns([1, 1, 3])
        if f1.button("👍 도움됐어요"):
            res["feedback"] = True
        if f2.button("👎 아쉬워요"):
            res["feedback"] = False
        if res["feedback"] is not None:
            track("feedback", helpful=res["feedback"], score=score, calc_id=res["calc_id"])
            st.rerun()
    else:
        st.write("피드백 감사합니다! 🙏")

    if st.button("🔗 친구에게 공유하기"):
        track("share_click", score_band=g["grade"])
        st.code("https://<배포주소>.streamlit.app/?ref=share", language=None)

with st.expander("ℹ️ 이 시뮬레이터에 대해"):
    st.markdown(
        "- [Kaggle 'Give Me Some Credit'](https://www.kaggle.com/c/GiveMeSomeCredit) 데이터(미국 대출자 15만 명, 2011)로 만든 **학습용 모델**이며, 실제 신용평가사(KCB·NICE) 점수와는 다릅니다.\n"
        "- 소득은 1달러 = 1,400원으로 환산합니다.\n"
        "- 서비스 개선을 위해 점수·등급과 버튼 클릭만 익명으로 기록하며, 입력하신 숫자 원본은 저장하지 않습니다."
    )

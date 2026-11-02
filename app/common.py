"""페이지들이 공유하는 로딩·사용자 식별·로깅·손익 계산."""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import scorecard as sc  # noqa: E402,F401
import events  # noqa: E402

KRW_PER_USD = 1400
SOURCES = {
    "amnesty": ("연내 빚 갚으면 '신용사면'된다…5천만원 이하 기록삭제 (SBS Biz, 2025.8)",
                "https://biz.sbs.co.kr/amp/article/20000252645"),
    "thinfile": ("청년·주부 신용등급 높아진다…씬파일러 별도 대안평가 개발 착수 (SBS Biz, 2026.7)",
                 "https://biz.sbs.co.kr/amp/article/20000321310"),
    "altdata": ("소비생활 데이터 활용한 신용평가…공정 대출·새 불평등 '두 얼굴' (경향신문, 2026.6)",
                "https://www.khan.co.kr/article/202606162036005/amp"),
    "aiact": ("AI 기본법 시행과 금융권 고영향 AI (비즈니스워치, 2026.1)",
              "https://news.bizwatch.co.kr/article/finance/2026/01/23/0033"),
    "data": ("Kaggle, Give Me Some Credit (2011)", "https://www.kaggle.com/c/GiveMeSomeCredit"),
}


# ------------------------------------------------------------------ 데이터
@st.cache_resource
def load_card(name="scorecard"):
    return json.loads((ROOT / f"models/{name}.json").read_text())


@st.cache_resource
def load_policy():
    return json.loads((ROOT / "models/policy.json").read_text())


@st.cache_resource
def load_artifacts():
    return json.loads((ROOT / "models/policy_artifacts.json").read_text())


@st.cache_data
def score_table() -> pd.DataFrame:
    """테스트셋 점수별 정상·부도 인원 (score, good, bad)."""
    d = pd.DataFrame(load_artifacts()["score_counts"], columns=["score", "target", "n"])
    t = d.pivot_table(index="score", columns="target", values="n", fill_value=0, aggfunc="sum")
    return t.rename(columns={0: "good", 1: "bad"}).reset_index()


def source_link(key) -> str:
    title, url = SOURCES[key]
    return f"[{title}]({url})"


# ------------------------------------------------------------------ 사용자·로깅
def identify():
    ss = st.session_state
    if "uid" not in ss:  # URL의 익명 ID를 이어받아 재방문(리텐션)을 추적
        ss["uid"] = st.query_params.get("uid") or uuid.uuid4().hex[:12]
        ss["ref"] = st.query_params.get("ref", "direct")
        ss["session_id"] = uuid.uuid4().hex
    if st.query_params.get("uid") != ss["uid"]:  # 페이지 이동 후에도 URL에 유지
        st.query_params["uid"] = ss["uid"]
    uid = ss["uid"]
    variant = "A" if int(hashlib.md5(uid.encode()).hexdigest(), 16) % 2 == 0 else "B"
    return uid, ss["session_id"], variant


def track(event, **props):
    uid, sid, variant = identify()
    events.log(event, user_id=uid, session_id=sid, variant=variant, props=props)


def page_view(page: str):
    """세션당 페이지별 1회 기록."""
    seen = st.session_state.setdefault("_seen_pages", set())
    if page not in seen:
        seen.add(page)
        track("page_view", page=page, ref=st.session_state.get("ref", "direct"))


# ------------------------------------------------------------------ 등급·손익
def grade_of(score):
    for g in load_policy()["grades"]:
        if score >= g["min"]:
            return g
    return load_policy()["grades"][-1]


def decision_of(score):
    pol = load_policy()
    if score >= pol["approve_cutoff"]:
        return "✅ 승인 예상", "success"
    if score >= pol["review_cutoff"]:
        return "🟡 추가 심사 예상", "warning"
    return "⛔ 거절 예상", "error"


def unit_economics(margin_pct: float, lgd_pct: float) -> tuple[float, float]:
    """대출 1건(원금 1) 기준: 정상 상환 이익, 부도 손실."""
    return margin_pct / 100, lgd_pct / 100


def portfolio(good_appr, bad_appr, good_all, bad_all, gain, loss) -> dict:
    n = good_all + bad_all
    appr = good_appr + bad_appr
    return {
        "승인율": appr / n if n else 0.0,
        "승인자 부도율": bad_appr / appr if appr else 0.0,
        "부도 차단율": 1 - bad_appr / bad_all if bad_all else 0.0,
        "정상 거절율": 1 - good_appr / good_all if good_all else 0.0,
        "1인당 손익": (gain * good_appr - loss * bad_appr) / n if n else 0.0,
    }


def cutoff_curve(t: pd.DataFrame, gain, loss) -> pd.DataFrame:
    """점수 기준점별 포트폴리오 지표 (t: score, good, bad)."""
    t = t.sort_values("score", ascending=False)
    cg, cb = t["good"].cumsum(), t["bad"].cumsum()
    G, B = t["good"].sum(), t["bad"].sum()
    out = pd.DataFrame({"cutoff": t["score"].values, "good": cg.values, "bad": cb.values})
    n = G + B
    out["승인율"] = (out.good + out.bad) / n
    out["승인자 부도율"] = out.bad / (out.good + out.bad)
    out["1인당 손익"] = (gain * out.good - loss * out.bad) / n
    return out.sort_values("cutoff").reset_index(drop=True)


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def won(x):
    """원금 1억 원 대출 기준 손익 표시."""
    return f"{x * 1e8 / 1e4:,.0f}만 원"


def sidebar_note_v3():
    st.sidebar.caption("생활 금융 도우미는 2026년 10월 31일 기준 정부 발표·보도를 바탕으로 정리한 참고용 계산기입니다. 금융·법률 자문이 아닙니다.")


def sidebar_note():
    st.sidebar.caption("학습용 모델입니다. 미국 Kaggle 데이터(2011)로 만들었으며 실제 신용평가사 점수와 다릅니다.")
    st.sidebar.caption("분석 화면의 수치는 테스트셋 30,000명 집계입니다.")


# ------------------------------------------------------------------ v3 생활 금융 도우미
import finance_calc as fc  # noqa: E402,F401


@st.cache_resource
def load_rules():
    return json.loads((ROOT / "app/rules/rules_2026.json").read_text())


def krw(won: float, signed=False) -> str:
    """원 → '1억 2,345만 원' 형식."""
    if won is None or (isinstance(won, float) and (np.isinf(won) or np.isnan(won))):
        return "제한 없음"
    sign = "-" if won < 0 else ("+" if signed and won > 0 else "")
    w = abs(won)
    eok, man = int(w // 1e8), int(round((w % 1e8) / 1e4))
    if man == 10000:
        eok, man = eok + 1, 0
    if eok and man:
        s = f"{eok}억 {man:,}만 원"
    elif eok:
        s = f"{eok}억 원"
    elif man:
        s = f"{man:,}만 원"
    else:
        s = f"{w:,.0f}원"
    return sign + s


def rule_sources(section: str, label="근거 자료"):
    r = load_rules()
    srcs = r[section].get("sources", []) if isinstance(r.get(section), dict) else []
    if srcs:
        with st.expander(f"📎 {label} (기준일 {r['as_of']})"):
            if r[section].get("note"):
                st.caption(r[section]["note"])
            for s in srcs:
                st.markdown(f"- [{s['title']}]({s['url']})")


def v3_disclaimer():
    r = load_rules()
    st.caption(f"ⓘ {r['disclaimer']} (기준일 {r['as_of']})")


def eok(won: float) -> str:
    """지표 카드용 짧은 표기: 1억 이상은 '3.13억 원', 미만은 '9,583만 원'."""
    if won is None or (isinstance(won, float) and np.isinf(won)):
        return "제한 없음"
    return f"{won / 1e8:,.2f}억 원" if abs(won) >= 1e8 else krw(won)

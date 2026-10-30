"""운영 대시보드 (로컬 실행용).

  streamlit run analytics/dashboard.py                                  # 실제 로그
  streamlit run analytics/dashboard.py -- --db logs/events_synthetic.db # 가상 로그
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--db", default=None)
args, _ = ap.parse_known_args()
db = args.db or str(analyze.ROOT / "logs/events.db")

st.set_page_config(page_title="시뮬레이터 대시보드", layout="wide")
st.title("📈 신용점수 시뮬레이터 운영 대시보드")
if "synthetic" in db:
    st.warning("가상(synthetic) 로그입니다. 실제 성과로 인용하지 마세요.")

res = analyze.run_all(analyze.snapshot(db))
da, fn, ab, sec, ret = (res[k] for k in ["daily_active", "funnel", "ab_helpful", "ab_secondary", "retention"])

k = st.columns(4)
k[0].metric("누적 방문자", f"{int(fn.step1_visit.sum()):,}")
k[1].metric("점수 계산 전환율", f"{fn.step2_calc.sum() / fn.step1_visit.sum():.1%}")
k[2].metric("도움됨 비율", f"{ab.helpful_users.sum() / max(ab.viewers.sum(), 1):.1%}")
k[3].metric("D1~7 재방문율", f"{(ret.d1_7 * ret.users).sum() / max(ret.users.sum(), 1):.1%}")

c1, c2 = st.columns(2)
c1.subheader("일별 방문자 · 계산자")
c1.line_chart(da.set_index("day")[["dau", "calc_users"]])
c2.subheader("퍼널 (실험군별)")
steps = ["step1_visit", "step2_calc", "step3_result", "step4_feedback", "step5_share"]
c2.bar_chart(fn.set_index("variant")[steps].T, stack=False)

st.subheader("A/B 테스트: 기본형(A) vs 코칭형(B)")
if len(ab) == 2 and ab.viewers.min() >= 30:
    t = analyze.ab_test(ab)
    a, b, c = st.columns(3)
    a.metric("A 도움됨", f"{t['A']:.1%}", help=f"n={t['n_A']}")
    b.metric("B 도움됨", f"{t['B']:.1%}", f"{t['lift_pp'] * 100:+.1f}%p")
    c.metric("p-value", f"{t['p_value']:.3f}", "유의" if t["p_value"] < .05 else "유의하지 않음",
             delta_color="normal" if t["p_value"] < .05 else "off")
    st.caption(f"95% CI [{t['ci95'][0] * 100:+.1f}, {t['ci95'][1] * 100:+.1f}]%p · "
               f"+5%p 검출에 필요한 표본 군당 {t['n_per_group_for_5pp']:,}명")
else:
    st.info("군별 결과 조회자가 30명 이상 모이면 검정 결과가 표시됩니다.")
st.dataframe(sec, hide_index=True)

c3, c4 = st.columns(2)
c3.subheader("유입 경로")
c3.dataframe(res["acquisition"], hide_index=True)
c4.subheader("사용자 등급 분포")
c4.bar_chart(res["grade_mix"].set_index("grade")["share"])

"""이벤트 로그 분석: 퍼널 · 리텐션 · A/B 테스트.

사용법
  python analytics/analyze.py                        # 운영 DB(DATABASE_URL 또는 logs/events.db)
  python analytics/analyze.py --db logs/events_synthetic.db   # 가상 로그로 연습
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
SQL = (Path(__file__).with_name("queries.sql")).read_text()


def load_queries() -> dict[str, str]:
    parts = re.split(r"^-- name: (\w+)\s*$", SQL, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def snapshot(db: str | None) -> sqlite3.Connection:
    """운영 DB 전체를 메모리 SQLite로 복사 → 같은 SQL로 분석."""
    if db:
        src = sqlite3.connect(db)
        df = pd.read_sql("SELECT * FROM events", src)
    else:
        sys.path.insert(0, str(ROOT / "app"))
        import events
        df = pd.read_sql("SELECT * FROM events", events.engine())
    con = sqlite3.connect(":memory:")
    df["ts"] = pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    df.to_sql("events", con, index=False)
    return con


def run_all(con) -> dict[str, pd.DataFrame]:
    return {name: pd.read_sql(q, con) for name, q in load_queries().items()}


def ab_test(df: pd.DataFrame, success="helpful_users", total="viewers") -> dict:
    """두 비율 차이에 대한 z-검정 + 95% 신뢰구간 + 검정력 점검."""
    a, b = df.set_index("variant").loc["A"], df.set_index("variant").loc["B"]
    pa, pb = a[success] / a[total], b[success] / b[total]
    p = (a[success] + b[success]) / (a[total] + b[total])
    se0 = np.sqrt(p * (1 - p) * (1 / a[total] + 1 / b[total]))
    z = (pb - pa) / se0
    pval = 2 * (1 - stats.norm.cdf(abs(z)))
    se = np.sqrt(pa * (1 - pa) / a[total] + pb * (1 - pb) / b[total])
    ci = (pb - pa - 1.96 * se, pb - pa + 1.96 * se)
    # 현재 A 비율에서 +5%p를 80% 검정력으로 잡으려면 군당 몇 명 필요한가
    d = 0.05
    n_need = int(np.ceil(((1.96 + 0.84) ** 2 * 2 * pa * (1 - pa)) / d ** 2))
    return {"A": pa, "B": pb, "lift_pp": pb - pa, "rel_lift": pb / pa - 1, "z": z, "p_value": pval,
            "ci95": ci, "n_per_group_for_5pp": n_need, "n_A": int(a[total]), "n_B": int(b[total])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    db = args.db or (None if os.environ.get("DATABASE_URL") else str(ROOT / "logs/events.db"))
    con = snapshot(db)
    res = run_all(con)
    pd.set_option("display.width", 140)
    for name in ["funnel", "ab_helpful", "ab_secondary", "acquisition", "grade_mix"]:
        print(f"\n== {name}\n{res[name].to_string(index=False)}")
    r = res["retention"]
    print(f"\n== retention (가중평균) D1={np.average(r.d1, weights=r.users):.1%} "
          f"D1-7={np.average(r.d1_7, weights=r.users):.1%}  코호트 {len(r)}개")

    ab = res["ab_helpful"]
    if len(ab) < 2 or ab["viewers"].min() < 30:
        print("\n== A/B: 군별 결과 조회자가 30명 미만이라 아직 검정하지 않습니다.")
        return res, None
    t = ab_test(ab)
    print("\n== A/B 결론 (1차 지표: 도움됐어요 비율)")
    print(f"A {t['A']:.1%} (n={t['n_A']}) vs B {t['B']:.1%} (n={t['n_B']}) → "
          f"{t['lift_pp']*100:+.1f}%p ({t['rel_lift']:+.0%}), p={t['p_value']:.4f}, "
          f"95% CI [{t['ci95'][0]*100:+.1f}, {t['ci95'][1]*100:+.1f}]%p")
    verdict = "B 채택" if t["p_value"] < 0.05 and t["lift_pp"] > 0 else (
        "A 유지" if t["p_value"] < 0.05 else "유의한 차이 없음 → 표본 추가 수집")
    print(f"판정: {verdict}  (+5%p 효과 검출에 필요한 표본: 군당 {t['n_per_group_for_5pp']}명)")
    return res, t


if __name__ == "__main__":
    main()

"""⚠️ 연습용 '가상' 이벤트 로그 생성기.

실제 사용자가 모이기 전에 분석 쿼리·대시보드를 검증하는 용도다.
포트폴리오나 이력서에는 반드시 실제 로그(logs/events.db 또는 운영 DB)의 결과만 쓸 것.
결과는 별도 파일 logs/events_synthetic.db 에 저장된다.
"""
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "events_synthetic.db"
rng = np.random.default_rng(7)

N_USERS, DAYS = 1200, 28
START = datetime(2026, 11, 2)
REFS = {"everytime": .35, "openchat": .25, "linkedin": .15, "share": .10, "direct": .15}
GRADES = {"A": .38, "B": .2, "C": .17, "D": .12, "E": .07, "F": .06}
# 가정한 '참' 효과: 코칭형(B)이 도움됨 비율이 조금 더 높다
HELPFUL = {"A": .34, "B": .41}


def main():
    OUT.parent.mkdir(exist_ok=True)
    OUT.unlink(missing_ok=True)
    con = sqlite3.connect(OUT)
    con.execute("CREATE TABLE events (event_id TEXT, ts TEXT, user_id TEXT, session_id TEXT, "
                "variant TEXT, event TEXT, props TEXT)")
    rows = []
    for _ in range(N_USERS):
        uid = uuid.uuid4().hex[:12]
        variant = "A" if rng.random() < .5 else "B"
        ref = rng.choice(list(REFS), p=list(REFS.values()))
        day0 = START + timedelta(days=int(rng.integers(0, DAYS)), hours=float(rng.uniform(8, 24)))
        grade = rng.choice(list(GRADES), p=list(GRADES.values()))
        visits = [day0]
        for d in range(1, 8):  # 재방문: 첫 주에 점점 감소
            if rng.random() < .10 / d ** .6:
                visits.append(day0 + timedelta(days=d, hours=float(rng.uniform(-3, 3))))
        for i, t in enumerate(visits):
            sid = uuid.uuid4().hex
            ev = lambda e, dt, **p: rows.append(
                (uuid.uuid4().hex, (t + timedelta(seconds=dt)).strftime("%Y-%m-%d %H:%M:%S"),
                 uid, sid, variant, e, json.dumps(p)))
            ev("page_view", 0, ref=ref if i == 0 else "direct")
            if rng.random() > .72 - (.1 if i else 0):
                continue  # 계산 안 하고 이탈
            n = 1 + rng.poisson(.8 if variant == "B" else .6)
            for k in range(n):
                ev("calc_submit", 30 + 40 * k, grade=str(grade), n_calc=k + 1)
                ev("result_view", 31 + 40 * k, grade=str(grade))
            if variant == "A" and rng.random() < .3:
                ev("tip_open", 60 + 40 * n)
            if rng.random() < .62:
                ev("feedback", 70 + 40 * n, helpful=bool(rng.random() < HELPFUL[variant] / .62))
            if rng.random() < (.06 if variant == "B" else .04):
                ev("share_click", 90 + 40 * n)
    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    print(f"가상 로그 {len(rows):,}건 → {OUT}")


if __name__ == "__main__":
    main()

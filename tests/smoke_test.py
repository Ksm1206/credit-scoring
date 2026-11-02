"""배포 전 자동 점검: 앱이 뜨고, 점수가 맞게 나오고, 로그가 DB에 쌓이는지 확인한다.

실행:  python tests/smoke_test.py
       DATABASE_URL=postgresql://... python tests/smoke_test.py   # 실제 DB로 점검
성공하면 마지막 줄에 "ALL PASSED"가 출력된다.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not os.environ.get("DATABASE_URL"):  # 기본: 임시 SQLite (운영 로그를 건드리지 않음)
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/smoke.db"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "app")]

import scorecard as sc  # noqa: E402
from sqlalchemy import text  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import events  # noqa: E402

card = json.loads((ROOT / "models/scorecard.json").read_text())
ok = lambda msg: print(f"  OK  {msg}")

# 1) 점수표 단건 계산: 기획서 부록 A의 검증 사례(526점)를 재현
case = {"age": 30, "dependents": 0, "rev_util": 0.95, "debt_ratio": 0.30,
        "monthly_income": 300 * 10000 / 1400, "real_estate_loans": 0,
        "late_30_59": 1, "late_60_89": 0, "late_90": 0}
score, _ = sc.score_one(card, case)
assert score == 526, f"점수 불일치: {score}"
ok("점수 계산 526점 일치")

# 2) 앱 실행 → 계산 → 피드백 (A·B 두 실험군)
uids = {"A": "demoa0", "B": "demob2"}
for variant, uid in uids.items():
    at = AppTest.from_file(str(ROOT / "app/views/my_score.py"), default_timeout=90)
    at.query_params["uid"] = uid
    at.run()
    assert not at.exception, at.exception
    at.slider[0].set_value(95)
    at.number_input[4].set_value(1)          # 30~59일 연체 1회
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.metric[0].value == "526점", at.metric[0].value
    labels = [b.label for b in at.button]
    assert ("점수 올리는 방법 보기" in labels) == (variant == "A"), f"{variant}군 화면 구성 이상"
    next(b for b in at.button if "도움됐어요" in b.label).click().run()
    assert not at.exception, at.exception
    ok(f"{variant}군 화면·계산·피드백 정상")

# 3) 분석 화면 4개가 오류 없이 뜨고, 핵심 수치가 노트북 결과와 같은지
expect = {
    "policy": ("승인자 부도율", "2.4%"),          # 558점 기준 (노트북: 2.39%)
    "amnesty": ("사면 대상", "5,333명"),
    "fairness": None,
    "mortgage_us": ("점수", None),
    "model_card": ("점수 분포 안정성 PSI (학습→테스트)", "0.0003"),
}
for page, chk in expect.items():
    at = AppTest.from_file(str(ROOT / f"app/views/{page}.py"), default_timeout=90)
    at.run()
    assert not at.exception, f"{page}: {at.exception}"
    if chk:
        got = {m.label: m.value for m in at.metric}
        assert chk[0] in got and (chk[1] is None or got[chk[0]] == chk[1]), f"{page}: {chk[0]}={got.get(chk[0])} (기대 {chk[1]})"
    ok(f"{page} 화면 정상")

# 4) v3 생활 금융 도우미: 진입 화면(내비게이션)과 계산기 5개
at = AppTest.from_file(str(ROOT / "app/app.py"), default_timeout=90)
at.query_params["uid"] = "demoa0"
at.run()
assert not at.exception, f"app.py: {at.exception}"
at.button[0].click().run()                                   # 기본값으로 '내 혜택 찾기'
assert not at.exception, f"benefits: {at.exception}"
got = {m.label: m.value for m in at.metric}
assert got.get("나에게 해당하는 항목", "0개") != "0개", got
ok(f"내 금융 혜택 찾기 정상 (항목 {got['나에게 해당하는 항목']}, 연간 {got.get('연간 아낄 수 있는 돈 (추정)')})")
for page in ["v3_refinance", "v3_rate_cut", "v3_mortgage", "v3_relief"]:
    at = AppTest.from_file(str(ROOT / f"app/views/{page}.py"), default_timeout=90)
    at.run()
    assert not at.exception, f"{page}: {at.exception}"
    ok(f"{page} 화면 정상 ({', '.join(f'{m.label}={m.value}' for m in at.metric[:2])})")

# 5) 이벤트가 DB에 기록됐는지 (로깅 실패는 화면에 드러나지 않으므로 직접 확인)
with events.engine().connect() as c:
    rows = c.execute(text("SELECT variant, event FROM events WHERE user_id IN ('demoa0','demob2')")).fetchall()
got = {(v, e) for v, e in rows}
for v in "AB":
    for e in ["page_view", "calc_submit", "result_view", "feedback"]:
        assert (v, e) in got, f"로그 누락: {v} {e}  (DB: {events.engine().url.render_as_string(hide_password=True)})"
ok(f"이벤트 {len(rows)}건 DB 기록 확인 ({events.engine().dialect.name})")

print("ALL PASSED")

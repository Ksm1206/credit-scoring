"""생활 금융 계산 로직 단위 테스트: python -m pytest tests/test_finance_calc.py -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import finance_calc as fc  # noqa: E402

RULES = json.loads((ROOT / "app/rules/rules_2026.json").read_text())


def test_monthly_payment_known_value():
    # 1억, 연 4%, 30년 원리금균등 → 약 477,415원 (표준 공식 검산값)
    assert fc.monthly_payment(1e8, 4.0, 360) == pytest.approx(477415.27, abs=1)


def test_schedule_repays_principal_all_methods():
    for m in fc.METHODS:
        s = fc.schedule(5e7, 5.0, 60, m)
        assert sum(p for p, _ in s) == pytest.approx(5e7, rel=1e-9)


def test_interest_ordering():
    # 같은 조건이면 이자는 원금균등 < 원리금균등 < 만기일시
    a, b, c = (fc.total_interest(1e8, 5.0, 120, m) for m in ("원금균등", "원리금균등", "만기일시"))
    assert a < b < c
    assert c == pytest.approx(1e8 * 0.05 / 12 * 120)


def test_prepayment_fee_sliding_and_exempt():
    assert fc.prepayment_fee(1e8, 0.6, 0, 360) == pytest.approx(600000)
    assert fc.prepayment_fee(1e8, 0.6, 18, 360) == pytest.approx(300000)   # 3년 중 절반 경과
    assert fc.prepayment_fee(1e8, 0.6, 36, 360) == 0
    assert fc.prepayment_fee(1e8, 0.6, 50, 360) == 0
    assert fc.prepayment_fee(1e7, 0.4, 6, 12) == pytest.approx(1e7 * 0.004 * 0.5)  # 1년 만기는 1년 기준


def test_refinance_net_and_breakeven():
    r = fc.refinance(1e8, 5.0, 4.0, 240, "원리금균등", 12, 360, 0.6, extra_cost=0)
    assert r.fee == pytest.approx(400000)
    assert r.interest_saving > 0 and r.net_saving == pytest.approx(r.interest_saving - r.fee)
    assert r.breakeven_month is not None and r.breakeven_month < 12
    assert r.cumulative[-1] == pytest.approx(r.net_saving, rel=1e-6)
    worse = fc.refinance(1e8, 4.0, 4.5, 240, "원리금균등", 12, 360, 0.6)
    assert worse.net_saving < 0 and worse.breakeven_month is None


def test_principal_from_payment_inverts_payment():
    pay = fc.monthly_payment(3e8, 4.5, 360)
    assert fc.principal_from_payment(pay * 12, 4.5, 360) == pytest.approx(3e8, rel=1e-9)


def test_mortgage_limit_binding_constraints():
    sd = RULES["stress_dsr"]
    seoul = RULES["mortgage"]["regions"]["서울 전역·경기 규제지역"]
    caps = RULES["mortgage"]["price_caps"]
    kw = dict(rate=4.0, term_months=360, existing_annual=0, dsr_cap_pct=40, price_caps=caps)
    # 고소득 + 20억 주택(서울) → 가격 상한 4억이 묶임
    r = fc.mortgage_limit(price=20e8, income=3e8, region=seoul, first_time=False,
                          stress_rate=sd["stress_rate"]["수도권·규제지역 주택담보대출"], type_ratio=1.0, **kw)
    assert r["binding"] == "가격 상한" and r["limit"] == 4e8
    # 연소득 5천, 서울 8억 → DSR이 묶임, 스트레스 금리로 한도 감소
    r = fc.mortgage_limit(price=8e8, income=5e7, region=seoul, first_time=False,
                          stress_rate=3.0, type_ratio=1.0, **kw)
    assert r["binding"] == "DSR" and r["stress_loss"] > 0
    assert r["applied_stress"] == 3.0
    # 혼합형은 스트레스 80%만 반영 → 변동형보다 한도가 크다
    mixed = fc.mortgage_limit(price=8e8, income=5e7, region=seoul, first_time=False,
                              stress_rate=3.0, type_ratio=sd["type_ratio"]["혼합형(5년 고정)"], **kw)
    assert mixed["by_dsr"] > r["by_dsr"]
    # 지방은 가격 상한 없음, LTV 70%
    local = RULES["mortgage"]["regions"]["지방(비수도권)"]
    r = fc.mortgage_limit(price=4e8, income=2e8, region=local, first_time=False, stress_rate=0.75, type_ratio=1.0, **kw)
    assert r["by_cap"] == float("inf") and r["limit"] == pytest.approx(2.8e8)


def test_policy_loan_matching():
    m = lambda **k: {x["name"] for x in fc.policy_loan_matches(RULES, **k)}
    base = dict(age=40, bureau="KCB", vulnerable=False, has_overdue=False)
    assert m(income_man=3000, score=800, **base) == {"햇살론 일반보증"}
    assert m(income_man=3000, score=600, **base) == {"햇살론 일반보증", "햇살론 특례보증", "불법사금융예방대출"}
    assert m(income_man=4000, score=600, **base) == {"햇살론 일반보증", "불법사금융예방대출"}
    assert m(income_man=4000, score=800, **base) == set()
    assert "햇살론유스" in m(income_man=3000, score=900, **{**base, "age": 27})
    assert "햇살론유스" not in m(income_man=6000, score=900, **{**base, "age": 27})  # 소득 초과
    assert "햇살론유스" not in m(income_man=3000, score=900, **{**base, "age": 35})  # 나이 초과

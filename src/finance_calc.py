"""생활 금융 계산 로직 (화면과 분리해 단위 테스트한다).

금액 단위는 원, 금리는 연 % (예: 4.5), 기간은 개월.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

METHODS = ("원리금균등", "원금균등", "만기일시")


# ---------------------------------------------------------------- 상환 스케줄
def monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """원리금균등 월 상환액."""
    if months <= 0:
        return 0.0
    r = annual_rate / 100 / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def schedule(principal: float, annual_rate: float, months: int, method: str = "원리금균등"):
    """월별 (원금상환, 이자) 리스트."""
    r = annual_rate / 100 / 12
    bal, out = principal, []
    pay = monthly_payment(principal, annual_rate, months)
    for m in range(1, months + 1):
        interest = bal * r
        if method == "원리금균등":
            prin = pay - interest
        elif method == "원금균등":
            prin = principal / months
        else:  # 만기일시
            prin = bal if m == months else 0.0
        prin = min(prin, bal)
        bal -= prin
        out.append((prin, interest))
    return out


def total_interest(principal, annual_rate, months, method="원리금균등") -> float:
    return sum(i for _, i in schedule(principal, annual_rate, months, method))


# ---------------------------------------------------------------- 중도상환수수료
def prepayment_fee(amount: float, fee_rate_pct: float, elapsed_months: int, term_months: int,
                   exempt_months: int = 36) -> float:
    """수수료 = 상환금액 × 요율 × 남은 기간 / 기준 기간.

    기준 기간은 약정 기간과 면제 기간(통상 3년) 중 짧은 쪽. 기준 기간이 지나면 0원.
    """
    base = min(term_months, exempt_months)
    remain = max(base - elapsed_months, 0)
    return amount * fee_rate_pct / 100 * remain / base if base > 0 else 0.0


# ---------------------------------------------------------------- 갈아타기
@dataclass
class RefinanceResult:
    cur_monthly: float
    new_monthly: float
    interest_saving: float      # 남은 기간 총 이자 차이 (+면 절약)
    fee: float                  # 중도상환수수료
    extra_cost: float           # 기타 비용 (인지세·설정비 등)
    net_saving: float
    breakeven_month: int | None  # 누적 절약액이 비용을 넘는 달
    cumulative: list             # 월별 누적 순절약액


def refinance(balance, cur_rate, new_rate, remain_months, method, elapsed_months, term_months,
              fee_rate_pct, extra_cost=0.0, exempt_months=36) -> RefinanceResult:
    cur = schedule(balance, cur_rate, remain_months, method)
    new = schedule(balance, new_rate, remain_months, method)
    fee = prepayment_fee(balance, fee_rate_pct, elapsed_months, term_months, exempt_months)
    cost = fee + extra_cost
    cum, run, be = [], -cost, None
    for m, ((p1, i1), (p2, i2)) in enumerate(zip(cur, new), 1):
        run += (p1 + i1) - (p2 + i2)
        cum.append(run)
        if be is None and run >= 0:
            be = m
    saving = sum(i for _, i in cur) - sum(i for _, i in new)
    first = lambda s: s[0][0] + s[0][1] if s else 0.0
    return RefinanceResult(first(cur), first(new), saving, fee, extra_cost, saving - cost, be, cum)


# ---------------------------------------------------------------- 금리인하요구권
def rate_cut_saving(balance, cur_rate, cut_pp, remain_months, method="원리금균등") -> dict:
    before = total_interest(balance, cur_rate, remain_months, method)
    after = total_interest(balance, max(cur_rate - cut_pp, 0), remain_months, method)
    yearly = sum(i for _, i in schedule(balance, cur_rate, min(12, remain_months), method)) - \
        sum(i for _, i in schedule(balance, max(cur_rate - cut_pp, 0), min(12, remain_months), method))
    return {"total": before - after, "first_year": yearly}


# ---------------------------------------------------------------- 주담대 한도 (LTV · 가격 상한 · DSR)
def principal_from_payment(annual_payment: float, annual_rate: float, months: int) -> float:
    """연간 상환 여력으로 빌릴 수 있는 원리금균등 대출 원금 (월 상환액 역산)."""
    if annual_payment <= 0:
        return 0.0
    pay = annual_payment / 12
    r = annual_rate / 100 / 12
    if r == 0:
        return pay * months
    return pay * (1 - (1 + r) ** -months) / r


def existing_annual_payment(credit_balance: float, credit_rate: float, other_monthly: float,
                            credit_term_years: int = 5) -> float:
    """DSR 산정용 기존 부채 연 원리금. 신용대출은 규정상 5년 분할상환으로 가정."""
    credit = monthly_payment(credit_balance, credit_rate, credit_term_years * 12) * 12 if credit_balance else 0.0
    return credit + other_monthly * 12


def mortgage_limit(price: float, income: float, rate: float, term_months: int, region: dict,
                   first_time: bool, existing_annual: float, stress_rate: float, type_ratio: float,
                   dsr_cap_pct: float, price_caps: list) -> dict:
    """세 가지 한도 중 가장 작은 값이 실제 한도. 금액 단위 원."""
    ltv_pct = region["ltv_first_time"] if first_time else region["ltv_no_house"]
    by_ltv = price * ltv_pct / 100
    by_cap = math.inf
    if region["price_caps"]:
        eok = price / 1e8
        by_cap = next(c["cap"] for c in price_caps if eok <= c["max_price"]) * 1e8
    applied_stress = stress_rate * type_ratio
    capacity = income * dsr_cap_pct / 100 - existing_annual
    by_dsr = principal_from_payment(capacity, rate + applied_stress, term_months)
    by_dsr_nostress = principal_from_payment(capacity, rate, term_months)
    limits = {"LTV": by_ltv, "가격 상한": by_cap, "DSR": by_dsr}
    binding = min(limits, key=limits.get)
    final = max(min(limits.values()), 0.0)
    return {"limit": final, "binding": binding, "by_ltv": by_ltv, "by_cap": by_cap, "by_dsr": by_dsr,
            "by_dsr_nostress": by_dsr_nostress, "ltv_pct": ltv_pct, "applied_stress": applied_stress,
            "stress_loss": max(by_dsr_nostress - by_dsr, 0.0),
            "monthly_payment": monthly_payment(final, rate, term_months)}


# ---------------------------------------------------------------- 정책서민금융 자격
def policy_loan_matches(rules: dict, age: int, income_man: float, score: int | None, bureau: str,
                        vulnerable: bool, has_overdue: bool) -> list[dict]:
    """조건에 맞을 가능성이 있는 상품 목록. income_man: 연소득(만원)."""
    pl = rules["policy_loans"]
    low = score is not None and score <= pl["low_score_cutoff"][bureau]
    out = []
    g = pl["햇살론 일반보증"]
    if income_man <= g["income_max"] or (income_man <= g["alt_income_max"] and low):
        out.append({"name": "햇살론 일반보증", "rate": f"연 {g['rate_max']}% 이내", "limit": f"최대 {g['limit']:,}만 원",
                    "why": "연소득 3,500만 원 이하" if income_man <= g["income_max"] else "연소득 4,500만 원 이하 + 신용점수 하위 20%",
                    "desc": g["desc"]})
    s = pl["햇살론 특례보증"]
    if income_man <= s["income_max"] and low:
        out.append({"name": "햇살론 특례보증",
                    "rate": f"연 {s['rate_vulnerable']}%부터" if vulnerable else f"연 {s['rate_max']}%",
                    "limit": f"최대 {s['limit']:,}만 원", "why": "연소득 3,500만 원 이하 + 신용점수 하위 20%",
                    "desc": s["desc"]})
    y = pl["햇살론유스"]
    if age <= y["age_max"]:
        out.append({"name": "햇살론유스", "rate": "서민금융진흥원 확인", "limit": "서민금융진흥원 확인",
                    "why": f"만 {y['age_max']}세 이하 청년", "desc": y["desc"]})
    if low or has_overdue:
        p = pl["불법사금융예방대출"]
        out.append({"name": "불법사금융예방대출", "rate": f"연 {p['rate']}% (전액 상환 시 실질 {p['effective_rate_full_repay']}%)",
                    "limit": "소액 긴급자금", "why": "저신용·연체로 일반 대출이 어려운 경우", "desc": p["desc"]})
    return out

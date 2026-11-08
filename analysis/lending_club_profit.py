"""LendingClub 실제 상환 금액으로 승인 기준점 손익을 다시 검증합니다.

GMSC에는 대출 금액과 금리가 없어 손익을 "정상 +1, 부도 -6"처럼 1건당 같은 금액으로 가정했습니다.
이 가정이 결론, 즉 몇 점부터 승인할지를 얼마나 바꾸는지 실제 돈의 흐름이 있는 LendingClub으로 확인합니다.

설계
- 대상: 2007~2011년 실행된 36개월 만기 대출 중 회사 심사 기준을 통과한 대출.
  60개월 대출은 2011년 실행분이 자료 시점까지 만기가 안 돼 상환 중인 대출이 빠지므로
  부도율이 부풀려집니다. 그래서 만기가 모두 끝난 36개월 대출만 씁니다.
- 시간 기준 분할: 2007~2010년 실행분으로 학습하고, 그중 20%로 기준점을 고르고,
  2011년 실행분으로 평가합니다. GMSC 분석의 한계였던 랜덤 분할을 보완합니다.
- 변수: 신청 시점에 알 수 있는 정보만 씁니다. 대출 실행 이후에 생기는 값(누수 변수)과
  LendingClub이 매긴 금리·등급(회사 자체 심사 결과)은 넣지 않습니다.
- 손익
    · 동일 금액 가정: 정상 +1, 부도 -6 (GMSC 분석과 같음)
    · 실제 금액: 대출마다 (총 상환액 - 실행 금액). 이자 수입과 부도 손실, 회수액이 모두 반영된 실제 값

실행: python scripts/prepare_data.py 후
      python analysis/lending_club_profit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import scorecard as sc  # noqa: E402

FEATURES = ["loan_amnt", "annual_inc", "dti", "revol_util", "revol_bal", "inq_last_6mths",
            "delinq_2yrs", "pub_rec", "open_acc", "total_acc", "emp_length_years",
            "credit_history_months"]
LABELS = {"loan_amnt": "대출 신청 금액", "annual_inc": "연소득", "dti": "DTI",
          "revol_util": "리볼빙 사용률", "revol_bal": "리볼빙 잔액", "inq_last_6mths": "최근 6개월 조회 수",
          "delinq_2yrs": "2년 내 연체 수", "pub_rec": "공공 부정 기록", "open_acc": "보유 신용 계좌",
          "total_acc": "전체 신용 계좌", "emp_length_years": "근속 연수",
          "credit_history_months": "신용 이력 개월"}
GAIN, LOSS = 1.0, 6.0


def load() -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data/processed/lending_club_full.csv", low_memory=False,
                    parse_dates=["issue_d"])
    d = d[(d.term_months == 36) & (d.meets_credit_policy == 1)].copy()
    d["profit_usd"] = d.total_pymnt - d.funded_amnt
    return d


def fit(tr: pd.DataFrame):
    bins = sc.fit_binnings(tr, tr.target, features=FEATURES)
    feats = [f for f in FEATURES if bins[f].iv >= 0.02]
    while True:
        lr = LogisticRegression(C=1.0, max_iter=1000).fit(sc.woe_frame(tr, bins, feats), tr.target)
        wrong = [f for f, c in zip(feats, lr.coef_[0]) if c > 0]
        if not wrong:
            break
        feats = [f for f in feats if f not in wrong]
    return sc.build_scorecard(bins, feats, lr.coef_[0], lr.intercept_[0], sc.Scaling(600, 50, 20)), bins, feats


def curve(score, d: pd.DataFrame, cuts) -> pd.DataFrame:
    y, money = d.target.values, d.profit_usd.values
    rows = []
    for c in cuts:
        a = score >= c
        rows.append({
            "cutoff": c, "승인율": a.mean(),
            "승인자 부도율": y[a].mean() if a.any() else np.nan,
            "동일 금액 손익(1건당)": (GAIN * ((y == 0) & a).sum() - LOSS * ((y == 1) & a).sum()) / len(y),
            "실제 손익(USD, 1건당)": money[a].sum() / len(y),
        })
    return pd.DataFrame(rows)


def main():
    d = load()
    train_all = d[d.issue_d.dt.year <= 2010]
    te = d[d.issue_d.dt.year == 2011]
    tr, va = train_test_split(train_all, test_size=0.2, stratify=train_all.target, random_state=42)

    card, bins, feats = fit(tr)
    s_va, s_te = sc.score_frame(card, va), sc.score_frame(card, te)
    auc = roc_auc_score(te.target, sc.score_to_pd(s_te, card["scaling"]))
    auc_grade = roc_auc_score(te.target, te.int_rate)   # 참고: LendingClub 자체 금리의 순위력

    grid = np.arange(int(np.floor(s_va.min())), int(np.ceil(s_va.max())) + 1)
    cv, ct = curve(s_va, va, grid), curve(s_te, te, grid)
    cut_unit = int(cv.loc[cv["동일 금액 손익(1건당)"].idxmax(), "cutoff"])
    cut_money = int(cv.loc[cv["실제 손익(USD, 1건당)"].idxmax(), "cutoff"])
    at = ct.set_index("cutoff")

    approve_all = ct.iloc[0] if (s_te >= grid[0]).all() else curve(s_te, te, [-1e9]).iloc[0]
    summary = pd.DataFrame({
        "전원 승인": approve_all,
        f"동일 금액 가정 최적 ({cut_unit}점)": at.loc[cut_unit],
        f"실제 금액 기준 최적 ({cut_money}점)": at.loc[cut_money],
    }).T.drop(columns="cutoff")

    # 손실/이익 비율 가정별로, 동일 금액 가정이 실제 금액 최적과 얼마나 다른 승인율을 고르는지
    sens = []
    y_va = va.target.values
    for ratio in [3, 4, 6, 8, 10]:
        prof = [(((y_va == 0) & (s_va >= c)).sum() - ratio * ((y_va == 1) & (s_va >= c)).sum()) for c in grid]
        c = int(grid[int(np.argmax(prof))])
        sens.append({"손실/이익 비율 가정": ratio, "선택된 기준점": c,
                     "테스트 승인율": at.loc[c, "승인율"],
                     "테스트 실제 손익(USD, 1건당)": at.loc[c, "실제 손익(USD, 1건당)"]})
    sens = pd.DataFrame(sens)
    # 실제 데이터에서 부도 1건 손실 / 정상 1건 이익의 평균 비율
    real_ratio = -d.loc[d.target == 1, "profit_usd"].mean() / d.loc[d.target == 0, "profit_usd"].mean()

    out = ROOT / "reports" / "lending_club"
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "cutoff_summary.csv", encoding="utf-8-sig")
    sens.to_csv(out / "ratio_sensitivity.csv", index=False, encoding="utf-8-sig")
    ct.to_csv(out / "cutoff_curve_test.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"변수": f, "설명": LABELS[f], "IV": round(bins[f].iv, 4), "사용": f in feats}
                  for f in FEATURES]).to_csv(out / "features_iv.csv", index=False, encoding="utf-8-sig")
    meta = {"n_train": len(tr), "n_valid": len(va), "n_test": len(te),
            "bad_rate_train": float(train_all.target.mean()), "bad_rate_test": float(te.target.mean()),
            "auc_scorecard_test": float(auc), "auc_int_rate_test": float(auc_grade),
            "features_used": feats, "cut_unit": cut_unit, "cut_money": cut_money,
            "real_loss_to_gain_ratio": float(real_ratio),
            "avg_profit_good_usd": float(d.loc[d.target == 0, "profit_usd"].mean()),
            "avg_loss_bad_usd": float(-d.loc[d.target == 1, "profit_usd"].mean())}
    sc.save_json(meta, out / "summary.json")

    pd.set_option("display.width", 200)
    print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in meta.items()})
    print(summary.round(4).to_string())
    print(sens.round(4).to_string(index=False))


if __name__ == "__main__":
    main()

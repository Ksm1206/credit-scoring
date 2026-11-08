"""단조 구간화(monotonic binning) 비교 분석.

README 한계에 적어 둔 문제, 즉 debt_ratio와 monthly_income의 점수가 구간마다 오르내리는
비단조 문제를 해결하면 성능과 승인 손익이 어떻게 바뀌는지 기존 스코어카드와 비교합니다.

- 기존: 의사결정나무로 찾은 경계를 그대로 사용 (models/scorecard.json과 같은 방식)
- 단조: 같은 경계에서 출발해, 부도율 방향이 뒤집히는 이웃 구간을 하나씩 합쳐
        구간 순서대로 부도율이 한 방향으로만 움직이게 만듦
- 정제+단조: 비단조의 원인이 된 비정상 값을 먼저 별도 구간으로 떼어 낸 뒤 단조 구간화
    · 월소득 0 또는 1(2,239명): 실제 소득으로 보기 어려움 → 월소득은 특수 구간,
      이들의 debt_ratio는 소득으로 나눌 수 없어 금액이 기록됨 → 결측 구간
    · 월소득 결측자의 debt_ratio도 같은 이유로 결측 구간
    · debt_ratio가 정확히 0: 특수 구간
    · 부동산 담보대출 수: 0건(무주택)과 4건 이상(과다 차입)이 모두 위험한 U자형은
      업무적으로 설명되므로 단조를 강제하지 않음

운영 모델(models/scorecard.json)과 앱은 바꾸지 않고, 비교 결과만 reports/에 저장합니다.

실행: python scripts/prepare_data.py 후
      python analysis/monotonic_binning.py
"""
from __future__ import annotations

import json
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

GAIN, LOSS = 1.0, 6.0   # 노트북과 같은 손익 가정: 정상 승인 +1, 부도 승인 -6


def numeric_bad_rates(b: sc.Binning, x: pd.Series, y: pd.Series) -> np.ndarray:
    """특수코드와 결측을 뺀 숫자 구간들의 부도율 (구간 순서대로)."""
    lab = pd.Series(b.assign(x))
    t = pd.DataFrame({"bin": lab, "y": np.asarray(y)})
    rates = t.groupby("bin")["y"].mean()
    return np.array([rates.get(l, np.nan) for l in b.labels()])


def make_monotonic(b: sc.Binning, x: pd.Series, y: pd.Series) -> sc.Binning:
    """부도율이 구간 순서대로 한 방향으로만 움직일 때까지 이웃 구간을 합친다."""
    edges = list(b.edges)
    while len(edges) > 0:
        cur = sc.Binning(b.feature, edges, special=b.special)
        r = numeric_bad_rates(cur, x, y)
        d = np.diff(r)
        direction = np.sign(np.nansum(d)) or 1.0          # 전체 추세 방향
        bad = np.where(np.sign(d) == -direction)[0]
        if len(bad) == 0:
            break
        # 방향이 가장 크게 어긋나는 지점의 경계를 지워 두 구간을 합친다
        i = bad[np.argmax(np.abs(d[bad]))]
        edges.pop(i)
    return sc.Binning(b.feature, edges, special=b.special).fit_woe(x, y)


def is_monotonic(b: sc.Binning, x, y) -> bool:
    """특수·결측 구간을 뺀 숫자 구간의 부도율이 한 방향으로만 움직이는가."""
    d = np.diff(numeric_bad_rates(b, x, y))
    d = d[~np.isnan(d)]
    return bool(len(d) == 0 or (d >= 0).all() or (d <= 0).all())


U_SHAPE_OK = {"real_estate_loans"}


def clean(d: pd.DataFrame) -> pd.DataFrame:
    """비정상 값을 특수 코드(-1) 또는 결측으로 바꾼다. 서빙할 때도 같은 규칙을 적용해야 한다."""
    d = d.copy()
    inc_bad = d.monthly_income.notna() & (d.monthly_income <= 1)
    dti_missing = d.monthly_income.isna() | inc_bad
    d.loc[d.debt_ratio.eq(0) & ~dti_missing, "debt_ratio"] = -1.0
    d.loc[dti_missing, "debt_ratio"] = np.nan
    d.loc[inc_bad, "monthly_income"] = -1.0
    return d


def fit_card(bins, tr):
    feats = [f for f in sc.FEATURES if bins[f].iv >= 0.02]
    while True:
        lr = LogisticRegression(C=1.0, max_iter=1000).fit(sc.woe_frame(tr, bins, feats), tr.target)
        wrong = [f for f, c in zip(feats, lr.coef_[0]) if c > 0]
        if not wrong:
            break
        feats = [f for f in feats if f not in wrong]
    return sc.build_scorecard(bins, feats, lr.coef_[0], lr.intercept_[0], sc.Scaling(600, 50, 20)), feats


def evaluate(card, tr, va, te):
    s_va, s_te = sc.score_frame(card, va), sc.score_frame(card, te)
    p_te = sc.score_to_pd(s_te, card["scaling"])
    y = te.target.values
    c80 = np.quantile(s_va, 0.20)
    a = s_te >= c80
    profit80 = (GAIN * ((y == 0) & a).sum() - LOSS * ((y == 1) & a).sum()) / len(y)
    return {
        "AUC": roc_auc_score(y, p_te),
        "KS": sc.ks_stat(y, p_te),
        "승인율 80% 기준점": float(c80),
        "승인자 부도율": float(y[a].mean()),
        "1인당 손익": float(profit80),
        "PSI(train→test)": sc.psi(sc.score_frame(card, tr), s_te),
    }


def main():
    df = sc.load_gmsc(ROOT / "data/processed/gmsc_train.csv")
    tr, te = train_test_split(df, test_size=0.2, stratify=df.target, random_state=42)
    tr, va = train_test_split(tr, test_size=0.25, stratify=tr.target, random_state=42)

    base = sc.fit_binnings(tr, tr.target)
    mono = {f: make_monotonic(b, tr[f], tr.target) for f, b in base.items()}

    card_b, feats_b = fit_card(base, tr)
    card_m, feats_m = fit_card(mono, tr)

    rows = []
    for f in sc.FEATURES:
        rows.append({
            "변수": f, "설명": sc.LABELS_KO[f],
            "기존 구간 수": len(base[f].edges) + 1, "단조 구간 수": len(mono[f].edges) + 1,
            "기존 단조 여부": is_monotonic(base[f], tr[f], tr.target),
            "단조 후 단조 여부": is_monotonic(mono[f], tr[f], tr.target),
            "기존 IV": round(base[f].iv, 4), "단조 IV": round(mono[f].iv, 4),
            "기존 모델 사용": f in feats_b, "단조 모델 사용": f in feats_m,
        })
    by_feature = pd.DataFrame(rows)

    # 정제+단조: 비정상 값을 특수·결측 구간으로 분리한 뒤 단조 구간화
    tr_f, va_f, te_f = clean(tr), clean(va), clean(te)
    special = {"monthly_income": [-1.0], "debt_ratio": [-1.0]}
    base_f = {}
    for f in sc.FEATURES:
        sp = special.get(f, sc.SPECIAL_CODES.get(f, []))
        x = tr_f[f]
        xs = x.where(~x.isin(sp)) if sp else x
        base_f[f] = sc.Binning(f, sc.tree_edges(xs, tr_f.target, 6, 0.02), special=sp).fit_woe(x, tr_f.target)
    mono_f = {f: (b if f in U_SHAPE_OK else make_monotonic(b, tr_f[f], tr_f.target))
              for f, b in base_f.items()}
    card_f, feats_f = fit_card(mono_f, tr_f)
    for r in rows:
        f = r["변수"]
        r["정제+단조 구간 수"] = len(mono_f[f].edges) + 1
        r["정제+단조 단조 여부"] = is_monotonic(mono_f[f], tr_f[f], tr_f.target)
        r["정제+단조 IV"] = round(mono_f[f].iv, 4)
        r["정제+단조 모델 사용"] = f in feats_f
    by_feature = pd.DataFrame(rows)

    perf = pd.DataFrame({"기존 스코어카드": evaluate(card_b, tr, va, te),
                         "단조 스코어카드": evaluate(card_m, tr, va, te),
                         "정제+단조 스코어카드": evaluate(card_f, tr_f, va_f, te_f)}).T

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    by_feature.to_csv(out / "monotonic_binning_features.csv", index=False, encoding="utf-8-sig")
    perf.to_csv(out / "monotonic_binning_performance.csv", encoding="utf-8-sig")
    sc.save_json(card_f, out / "scorecard_monotonic_candidate.json")
    pd.set_option("display.width", 200)
    print(by_feature.to_string(index=False))
    print()
    print(perf.round(4).to_string())


if __name__ == "__main__":
    main()

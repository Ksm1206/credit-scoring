"""앱의 정책 분석 화면에 쓸 집계 데이터를 만든다.

- 노트북과 같은 분할(60/20/20, random_state=42)의 **테스트셋 30,000명**만 사용한다.
- 원본 행(Kaggle 데이터)은 재배포하지 않도록 **점수·그룹별 인원수 집계만** 저장한다.
- 출력: models/policy_artifacts.json, models/scorecard_noage.json

실행: python analysis/build_policy_artifacts.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import scorecard as sc  # noqa: E402

OUT = ROOT / "models"
LATE = ["late_30_59", "late_60_89", "late_90"]
AGE_BANDS = [(0, 29, "20대"), (30, 39, "30대"), (40, 49, "40대"), (50, 59, "50대"), (60, 200, "60대+")]
AMNESTY_SCOPES = {
    "minor": {"label": "30~59일 연체만 삭제", "cols": ["late_30_59"]},
    "mid": {"label": "30~89일 연체 삭제", "cols": ["late_30_59", "late_60_89"]},
    "all": {"label": "90일 이상 포함 전체 삭제", "cols": LATE},
}


def age_band(a):
    for lo, hi, name in AGE_BANDS:
        if lo <= a <= hi:
            return name
    return AGE_BANDS[-1][2]


def counts(df, keys):
    g = df.groupby(keys, observed=True).size().reset_index(name="n")
    return g.astype({k: (int if df[k].dtype.kind in "iuf" and k != "age_group" else str) for k in keys}).values.tolist()


def approval_curve(risk, y, step=0.005, seed=0):
    """위험이 낮은 순으로 승인율 r%까지 승인했을 때의 정상·부도 인원 (동점은 무작위)."""
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(risk)), risk))
    ys = np.asarray(y)[order]
    cg, cb = np.cumsum(ys == 0), np.cumsum(ys == 1)
    out = []
    for r in np.round(np.arange(0, 1 + 1e-9, step), 4):
        k = int(round(r * len(ys)))
        out.append([float(r), int(cg[k - 1]) if k else 0, int(cb[k - 1]) if k else 0])
    return out


def main():
    df = sc.load_gmsc(ROOT / "data/processed/gmsc_train.csv")
    tr, te = train_test_split(df, test_size=0.2, stratify=df.target, random_state=42)
    tr, va = train_test_split(tr, test_size=0.25, stratify=tr.target, random_state=42)
    te = te.reset_index(drop=True)

    card = json.loads((OUT / "scorecard.json").read_text())
    te["score"] = sc.score_frame(card, te).astype(int)
    tr_score = sc.score_frame(card, tr)
    p_sc = sc.score_to_pd(te["score"], card["scaling"])
    auc_sc = roc_auc_score(te.target, p_sc)
    assert abs(auc_sc - 0.8577) < 0.001, f"노트북과 다른 결과: AUC {auc_sc:.4f}"

    # ---------------------------------------------------------- 나이 제외 모델
    bins = sc.fit_binnings(tr, tr.target)
    feats = [f for f in card["features"] if f != "age"]
    while True:
        lr = LogisticRegression(C=1.0, max_iter=1000).fit(sc.woe_frame(tr, bins, feats), tr.target)
        wrong = [f for f, c in zip(feats, lr.coef_[0]) if c > 0]
        if not wrong:
            break
        feats = [f for f in feats if f not in wrong]
    card_na = sc.build_scorecard(bins, feats, lr.coef_[0], lr.intercept_[0], sc.Scaling(**card["scaling"]))
    sc.save_json(card_na, OUT / "scorecard_noage.json")
    te["score_noage"] = sc.score_frame(card_na, te).astype(int)
    auc_na = roc_auc_score(te.target, sc.score_to_pd(te["score_noage"], card["scaling"]))

    # ---------------------------------------------------------- LightGBM
    booster = lgb.Booster(model_file=str(OUT / "lgbm.txt"))
    p_gb = booster.predict(te[sc.FEATURES])
    auc_gb = roc_auc_score(te.target, p_gb)

    # ---------------------------------------------------------- 그룹 변수
    te["age_group"] = te["age"].map(age_band)
    special = te[LATE].isin([96, 98]).any(axis=1)
    te["clean"] = ((te[LATE].sum(axis=1) == 0) & ~special).astype(int)

    # ---------------------------------------------------------- 신용사면
    amnesty = {}
    for key, spec in AMNESTY_SCOPES.items():
        hit = (te[spec["cols"]] > 0).any(axis=1) & ~special
        moved = te.loc[hit].copy()
        moved[spec["cols"]] = 0
        moved["new_score"] = sc.score_frame(card, moved).astype(int)
        moved["orig_score"] = moved["score"]
        amnesty[key] = {
            "label": spec["label"], "n_affected": int(hit.sum()),
            "affected": counts(moved, ["orig_score", "new_score", "target"]),
            "by_age": counts(moved, ["age_group", "target"]),
        }

    # ---------------------------------------------------------- 모델 카드 지표
    def csi(f):
        bn = sc.Binning(f, card["features"][f]["edges"], card["features"][f]["special"])
        a = pd.Series(bn.assign(tr[f])).value_counts(normalize=True)
        b = pd.Series(bn.assign(te[f])).value_counts(normalize=True)
        idx = a.index.union(b.index)
        a, b = a.reindex(idx).fillna(1e-6).clip(1e-6), b.reindex(idx).fillna(1e-6).clip(1e-6)
        return float(((b - a) * np.log(b / a)).sum())

    artifacts = {
        "meta": {"created": str(date.today()), "n_test": int(len(te)), "bad_rate": float(te.target.mean()),
                 "source": "Kaggle Give Me Some Credit (2011), 테스트셋 30,000명 집계",
                 "age_groups": [b[2] for b in AGE_BANDS]},
        "score_counts": counts(te, ["score", "target"]),
        "approval_curves": {
            "스코어카드": approval_curve(-te["score"].values, te.target),
            "스코어카드(나이 제외)": approval_curve(-te["score_noage"].values, te.target),
            "LightGBM": approval_curve(p_gb, te.target),
        },
        "amnesty": amnesty,
        "fairness": {
            "with_age": counts(te, ["age_group", "clean", "score", "target"]),
            "no_age": counts(te, ["age_group", "clean", "score_noage", "target"]),
        },
        "model_card": {
            "auc": {"스코어카드": auc_sc, "스코어카드(나이 제외)": auc_na, "LightGBM": auc_gb},
            "ks": {"스코어카드": sc.ks_stat(te.target, p_sc),
                   "스코어카드(나이 제외)": sc.ks_stat(te.target, sc.score_to_pd(te["score_noage"], card["scaling"])),
                   "LightGBM": sc.ks_stat(te.target, p_gb)},
            "psi": sc.psi(tr_score, te["score"]),
            "csi": {f: csi(f) for f in card["features"]},
            "iv": {f: card["features"][f]["iv"] for f in card["features"]},
            "n_train": int(len(tr)), "n_valid": int(len(va)),
            "noage_features": feats,
        },
    }
    (OUT / "policy_artifacts.json").write_text(json.dumps(artifacts, ensure_ascii=False))

    # 콘솔 요약 (검산용)
    print(f"AUC  scorecard {auc_sc:.4f} | no-age {auc_na:.4f} | lgbm {auc_gb:.4f}")
    for k, a in amnesty.items():
        aff = pd.DataFrame(a["affected"], columns=["o", "n", "t", "c"])
        w = aff.c
        print(f"amnesty[{k}] affected {a['n_affected']:,} | bad rate {np.average(aff.t, weights=w):.1%} | "
              f"avg +{np.average(aff.n - aff.o, weights=w):.1f}pt")
    g = te.groupby("age_group").agg(n=("target", "size"), bad=("target", "mean"), s=("score", "mean"), s2=("score_noage", "mean"))
    print(g.round(3))
    print("size KB:", round((OUT / "policy_artifacts.json").stat().st_size / 1024, 1))


if __name__ == "__main__":
    main()

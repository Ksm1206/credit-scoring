"""프레디맥 주택담보대출 스코어카드: 숫자형(트리 구간화) + 범주형 WoE를 함께 다룬다.

v1(scorecard.py)의 구간화·스케일링을 재사용하고, 범주형 변수와 점수표 직렬화만 추가한다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

import scorecard as sc

NUMERIC = ["fico", "dti", "ltv", "rate_spread", "log_upb"]
CATEGORICAL = ["first_time", "purpose", "occupancy", "channel", "prop_type", "borrowers", "program"]
LABELS_KO = {
    "fico": "신용점수(FICO)", "dti": "DTI(%)", "ltv": "LTV(%)", "rate_spread": "금리 가산폭(같은 분기 중앙값 대비, %p)",
    "log_upb": "대출금액(로그)", "first_time": "생애최초 구입", "purpose": "대출 목적", "occupancy": "거주 형태",
    "channel": "대출 채널", "prop_type": "주택 유형", "borrowers": "차주 수", "program": "정책 프로그램",
}
CAT_KO = {
    "first_time": {"Y": "예", "N": "아니오", "9": "미상"},
    "purpose": {"P": "주택 구입", "C": "현금인출 재융자", "N": "일반 재융자", "R": "재융자(미분류)"},
    "occupancy": {"P": "실거주", "I": "투자용", "S": "세컨드하우스"},
    "channel": {"R": "직접(은행)", "C": "제휴(코레스폰던트)", "B": "중개(브로커)", "T": "기타"},
    "prop_type": {"SF": "단독주택", "PU": "계획단지(PUD)", "CO": "콘도", "MH": "조립식주택", "CP": "협동조합"},
    "borrowers": {"1": "1명", "2+": "2명 이상"},
    "program": {"none": "해당 없음", "H": "Home Possible(저소득 지원)", "F": "HFA(주택금융기관 지원)", "R": "기타"},
}


def add_features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    # 금리 수준은 시기(2021 vs 2023)에 따라 크게 달라 → 같은 분기 대출 중앙값 대비 '가산폭'만 위험 신호로 쓴다
    d["rate_spread"] = d["rate"] - d.groupby("orig_quarter")["rate"].transform("median")
    d["log_upb"] = np.log10(d["upb"])
    d["borrowers"] = np.where(d["n_borrowers"].fillna(1) >= 2, "2+", "1")
    d["program"] = d["program"].fillna("none")
    d["first_time"] = d["first_time"].fillna("9")
    return d


class CatBinning:
    """범주별 WoE. 표본 1% 미만 범주는 '기타'로 묶는다."""

    def __init__(self, feature, min_frac=0.01):
        self.feature, self.min_frac = feature, min_frac
        self.keep, self.woe, self.stats, self.iv = [], {}, [], 0.0

    def _map(self, x):
        x = pd.Series(x).astype(str)
        return x.where(x.isin(self.keep), "기타").to_numpy()

    def fit(self, x, y, eps=0.5):
        x = pd.Series(x).astype(str)
        share = x.value_counts(normalize=True)
        self.keep = share[share >= self.min_frac].index.tolist()
        t = pd.DataFrame({"bin": self._map(x), "y": np.asarray(y)})
        g = t.groupby("bin")["y"].agg(["count", "sum"]).rename(columns={"sum": "bad"})
        g["good"] = g["count"] - g["bad"]
        dg = (g["good"] + eps) / (g["good"].sum() + eps * len(g))
        db = (g["bad"] + eps) / (g["bad"].sum() + eps * len(g))
        g["woe"], g["bad_rate"] = np.log(dg / db), g["bad"] / g["count"]
        g["iv"] = (dg - db) * g["woe"]
        self.woe, self.iv = g["woe"].to_dict(), float(g["iv"].sum())
        self.stats = g.reset_index()[["bin", "count", "bad", "bad_rate", "woe", "iv"]].to_dict("records")
        return self

    def transform(self, x):
        return np.array([self.woe.get(b, 0.0) for b in self._map(x)])


def fit_all(df, y):
    bins = sc.fit_binnings(df, y, NUMERIC, max_bins=6, min_frac=0.03)
    for c in CATEGORICAL:
        bins[c] = CatBinning(c).fit(df[c], y)
    return bins


def woe_frame(df, bins, feats):
    return pd.DataFrame({f: bins[f].transform(df[f]) for f in feats}, index=df.index)


def build_card(bins, feats, coef, intercept, scaling: sc.Scaling) -> dict:
    n = len(feats)
    card = {"scaling": scaling.__dict__, "features": {}}
    for f, b in zip(feats, coef):
        bn = bins[f]
        pts = {str(k): round(-(b * w + intercept / n) * scaling.factor + scaling.offset / n) for k, w in bn.woe.items()}
        default = round(-(intercept / n) * scaling.factor + scaling.offset / n)
        cat = isinstance(bn, CatBinning)
        card["features"][f] = {
            "label_ko": LABELS_KO[f], "type": "categorical" if cat else "numeric",
            "edges": None if cat else bn.edges, "keep": bn.keep if cat else None,
            "coef": float(b), "points": pts, "default_points": default, "bins": bn.stats, "iv": bn.iv,
        }
    return card


def _bin_labels(spec, values):
    if spec["type"] == "categorical":
        v = pd.Series(values).astype(str)
        return v.where(v.isin(spec["keep"]), "기타").to_numpy()
    return sc.Binning("x", spec["edges"]).assign(values)


def score_frame(card, df) -> np.ndarray:
    total = np.zeros(len(df))
    for f, spec in card["features"].items():
        total += np.array([spec["points"].get(l, spec["default_points"]) for l in _bin_labels(spec, df[f])])
    return total


def score_one(card, values: dict):
    total, detail = 0, {}
    for f, spec in card["features"].items():
        lab = _bin_labels(spec, [values.get(f, np.nan)])[0]
        p = spec["points"].get(lab, spec["default_points"])
        total += p
        detail[f] = {"bin": lab, "points": p}
    return int(total), detail


def to_pd(score, scaling) -> np.ndarray:
    return sc.score_to_pd(score, scaling)

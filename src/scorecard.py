"""WoE 기반 신용평가 스코어카드 유틸리티.

노트북(학습)과 Streamlit 앱(서빙)이 같은 코드를 쓰도록 분리했다.
앱은 scikit-learn 없이 `scorecard.json`만 읽어 점수를 계산한다.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# 원본 컬럼명 → 짧은 이름
RENAME = {
    "RevolvingUtilizationOfUnsecuredLines": "rev_util",
    "age": "age",
    "NumberOfTime30-59DaysPastDueNotWorse": "late_30_59",
    "DebtRatio": "debt_ratio",
    "MonthlyIncome": "monthly_income",
    "NumberOfOpenCreditLinesAndLoans": "open_credit_lines",
    "NumberOfTimes90DaysLate": "late_90",
    "NumberRealEstateLoansOrLines": "real_estate_loans",
    "NumberOfTime60-89DaysPastDueNotWorse": "late_60_89",
    "NumberOfDependents": "dependents",
}
FEATURES = list(RENAME.values())
LABELS_KO = {
    "rev_util": "리볼빙 한도 사용률",
    "age": "나이",
    "late_30_59": "30~59일 연체 횟수(2년)",
    "debt_ratio": "DTI(월 부채상환액 / 월소득)",
    "monthly_income": "월소득(USD)",
    "open_credit_lines": "보유 대출·카드 수",
    "late_90": "90일 이상 연체 횟수",
    "real_estate_loans": "부동산 담보대출 수",
    "late_60_89": "60~89일 연체 횟수(2년)",
    "dependents": "부양가족 수",
}
# 연체 횟수 96/98은 실제 횟수가 아니라 특수코드 → 별도 구간
SPECIAL_CODES = {"late_30_59": [96, 98], "late_90": [96, 98], "late_60_89": [96, 98]}


def load_gmsc(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns=RENAME)
    df = df[df["age"] > 0].reset_index(drop=True)  # age=0 1건 제거
    return df[["id"] + FEATURES + ["target"]] if "id" in df.columns else df[FEATURES + ["target"]]


# ------------------------------------------------------------------ binning
def tree_edges(x: pd.Series, y: pd.Series, max_bins=6, min_frac=0.05) -> list[float]:
    """의사결정나무로 부도율 차이가 큰 지점을 찾아 구간 경계로 쓴다."""
    from sklearn.tree import DecisionTreeClassifier

    m = x.notna()
    tree = DecisionTreeClassifier(max_leaf_nodes=max_bins, min_samples_leaf=min_frac,
                                  random_state=0)
    tree.fit(x[m].to_frame(), y[m])
    th = tree.tree_.threshold[tree.tree_.feature >= 0]
    return sorted(float(t) for t in set(th))


@dataclass
class Binning:
    feature: str
    edges: list[float]                       # 내부 경계 (-inf, e1], (e1, e2], ..., (ek, inf)
    special: list[float] = field(default_factory=list)
    woe: dict[str, float] = field(default_factory=dict)
    stats: list[dict] = field(default_factory=list)
    iv: float = 0.0

    def labels(self) -> list[str]:
        e = [-math.inf] + self.edges + [math.inf]
        fmt = lambda v: "-inf" if v == -math.inf else ("inf" if v == math.inf else f"{v:g}")
        return [f"({fmt(a)}, {fmt(b)}]" for a, b in zip(e[:-1], e[1:])]

    def assign(self, x) -> np.ndarray:
        x = pd.Series(x, dtype="float64").reset_index(drop=True)
        idx = np.searchsorted(np.array(self.edges), x.to_numpy(), side="left")
        lab = np.array(self.labels(), dtype=object)[np.clip(idx, 0, len(self.edges))]
        lab = pd.Series(lab)
        lab[x.isna().to_numpy()] = "missing"
        if self.special:
            lab[x.isin(self.special).to_numpy()] = "special"
        return lab.to_numpy()

    def fit_woe(self, x, y, eps=0.5):
        lab = self.assign(x)
        t = pd.DataFrame({"bin": lab, "y": np.asarray(y)})
        g = t.groupby("bin")["y"].agg(["count", "sum"]).rename(columns={"sum": "bad"})
        g["good"] = g["count"] - g["bad"]
        tg, tb = g["good"].sum(), g["bad"].sum()
        g["dist_good"] = (g["good"] + eps) / (tg + eps * len(g))
        g["dist_bad"] = (g["bad"] + eps) / (tb + eps * len(g))
        g["woe"] = np.log(g["dist_good"] / g["dist_bad"])
        g["iv"] = (g["dist_good"] - g["dist_bad"]) * g["woe"]
        g["bad_rate"] = g["bad"] / g["count"]
        order = self.labels() + ["special", "missing"]
        g = g.reindex([o for o in order if o in g.index])
        self.woe = g["woe"].to_dict()
        self.iv = float(g["iv"].sum())
        self.stats = (g.reset_index()[["bin", "count", "bad", "bad_rate", "woe", "iv"]]
                      .to_dict("records"))
        return self

    def transform(self, x) -> np.ndarray:
        lab = self.assign(x)
        # 학습 때 없던 구간(예: 결측)은 WoE 0 = 평균 위험으로 처리
        return np.array([self.woe.get(l, 0.0) for l in lab])


def fit_binnings(df: pd.DataFrame, y: pd.Series, features=FEATURES, max_bins=6, min_frac=0.02) -> dict[str, Binning]:
    out = {}
    for f in features:
        sp = SPECIAL_CODES.get(f, [])
        x = df[f]
        xs = x.where(~x.isin(sp)) if sp else x
        b = Binning(f, tree_edges(xs, y, max_bins, min_frac), special=sp)
        out[f] = b.fit_woe(x, y)
    return out


def woe_frame(df, binnings, features) -> pd.DataFrame:
    return pd.DataFrame({f: binnings[f].transform(df[f]) for f in features}, index=df.index)


# ------------------------------------------------------------------ scaling
@dataclass
class Scaling:
    base_score: float = 600.0   # 이 점수일 때
    base_odds: float = 50.0     # 정상:부도 = 50:1
    pdo: float = 20.0           # 20점 오르면 odds 2배

    @property
    def factor(self):
        return self.pdo / math.log(2)

    @property
    def offset(self):
        return self.base_score - self.factor * math.log(self.base_odds)


def build_scorecard(binnings, features, coef, intercept, scaling=Scaling()) -> dict:
    """logit(P(bad)) = b0 + Σ b_i·WoE_i  →  구간별 정수 점수."""
    n = len(features)
    card = {"scaling": scaling.__dict__, "features": {}}
    for f, b in zip(features, coef):
        bn = binnings[f]
        pts = {lab: round(-(b * w + intercept / n) * scaling.factor + scaling.offset / n)
               for lab, w in bn.woe.items()}
        # 학습 때 없던 구간 → WoE 0
        default = round(-(intercept / n) * scaling.factor + scaling.offset / n)
        card["features"][f] = {
            "label_ko": LABELS_KO.get(f, f), "edges": bn.edges, "special": bn.special,
            "coef": float(b), "points": pts, "default_points": default,
            "bins": bn.stats, "iv": bn.iv,
        }
    return card


def score_one(card: dict, values: dict) -> tuple[int, dict]:
    """앱에서 쓰는 단건 점수 계산. sklearn 불필요."""
    total, detail = 0, {}
    for f, spec in card["features"].items():
        bn = Binning(f, spec["edges"], spec["special"])
        lab = bn.assign([values.get(f, np.nan)])[0]
        p = spec["points"].get(lab, spec["default_points"])
        total += p
        detail[f] = {"bin": lab, "points": p}
    return int(total), detail


def score_frame(card: dict, df: pd.DataFrame) -> np.ndarray:
    total = np.zeros(len(df))
    for f, spec in card["features"].items():
        bn = Binning(f, spec["edges"], spec["special"])
        lab = bn.assign(df[f])
        total += np.array([spec["points"].get(l, spec["default_points"]) for l in lab])
    return total


def score_to_pd(score, scaling: dict) -> np.ndarray:
    s = Scaling(**scaling)
    log_odds_good = (np.asarray(score, dtype=float) - s.offset) / s.factor
    return 1 / (1 + np.exp(log_odds_good))


# ------------------------------------------------------------------ metrics
def ks_stat(y, p) -> float:
    from sklearn.metrics import roc_curve
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def psi(expected, actual, bins=10) -> float:
    q = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    q[0], q[-1] = -np.inf, np.inf
    e = np.histogram(expected, q)[0] / len(expected)
    a = np.histogram(actual, q)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


def save_json(obj, path):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=float))

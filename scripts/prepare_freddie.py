"""Freddie Mac Single-Family Loan-Level Dataset (Release 48, 2026.10) → 대출 단위 분석 테이블.

입력: data/raw/freddie/sample_orig_YYYY.txt, sample_perf_YYYY.txt (연도별 무작위 5만 건 샘플)
출력: data/processed/freddie_loans.parquet, data/processed/freddie_report.json

부도 정의(업계 관행): 첫 납부 후 24개월(loan_age 0~24) 안에
  ① 90일 이상 연체(상태 코드 03 이상 또는 RA) 또는
  ② 부도성 종료(제3자 매각 02, 숏세일·상각 03, REO 처분 09, 부실채권 매각 15)
민감도용으로 코로나 상환유예(F)·재난(Y) 기간의 연체를 제외한 정의도 함께 만든다.

실행: python scripts/prepare_freddie.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/freddie"
OUT = ROOT / "data/processed"
WINDOW = 24

ORIG_COLS = [  # Release 48 레이아웃 (31열). 실제 값 분포로 위치를 확인함
    "fico", "first_pay", "first_time", "maturity", "msa", "mi_pct", "units", "occupancy", "cltv", "dti",
    "upb", "ltv", "rate", "channel", "ppm", "amort", "state", "prop_type", "zip3", "loan_id",
    "purpose", "term", "n_borrowers", "seller", "super_conforming", "pre_harp_id", "program",
    "relief_refi", "valuation_method", "interest_only", "vantage4",
]
PERF_USE = {0: "loan_id", 1: "period", 3: "delq", 4: "age", 8: "zb_code", 9: "zb_date",
            21: "actual_loss", 26: "zb_upb", 28: "disaster", 29: "assist"}
DEFAULT_ZB = {"02", "03", "09", "15"}
NA_CODES = {"fico": 9999, "dti": 999, "ltv": 999, "cltv": 999, "mi_pct": 999, "n_borrowers": 99, "units": 99}


def load_orig(year: int) -> pd.DataFrame:
    o = pd.read_csv(RAW / f"sample_orig_{year}.txt", sep="|", header=None, names=ORIG_COLS, dtype=str)
    num = ["fico", "mi_pct", "units", "cltv", "dti", "upb", "ltv", "rate", "term", "n_borrowers"]
    o[num] = o[num].apply(pd.to_numeric, errors="coerce")
    for c, na in NA_CODES.items():
        o.loc[o[c] == na, c] = np.nan
    o["vintage"] = year
    o["orig_quarter"] = o["loan_id"].str[1:5]                       # 예: 21Q1
    return o


def outcomes(year: int) -> pd.DataFrame:
    p = pd.read_csv(RAW / f"sample_perf_{year}.txt", sep="|", header=None, usecols=list(PERF_USE),
                    dtype=str).rename(columns=PERF_USE)
    p["age"] = pd.to_numeric(p["age"], errors="coerce")
    d = pd.to_numeric(p["delq"].replace({"RA": "99", "XX": np.nan}), errors="coerce")
    in_win = p["age"] <= WINDOW
    d90 = (d >= 3) | p["delq"].eq("RA")
    zb_def = p["zb_code"].isin(DEFAULT_ZB)
    relief = p["assist"].eq("F") | p["disaster"].eq("Y")
    p["def_any"] = in_win & (d90 | zb_def)
    p["def_strict"] = in_win & ((d90 & ~relief) | zb_def)
    p["d30"] = in_win & (d >= 1)
    p["prepaid"] = in_win & p["zb_code"].eq("01")
    loss = pd.to_numeric(p["actual_loss"], errors="coerce")
    g = p.groupby("loan_id")
    out = pd.DataFrame({
        "default24": g["def_any"].any(),
        "default24_strict": g["def_strict"].any(),
        "ever_30dpd24": g["d30"].any(),
        "prepaid24": g["prepaid"].any(),
        "max_age": g["age"].max(),
        "ever_relief": g.apply(lambda x: bool((x["assist"].eq("F") | x["disaster"].eq("Y")).any()), include_groups=False),
        "liquidated": g["zb_code"].agg(lambda s: s.isin(DEFAULT_ZB).any()),
    })
    zb = p[p["zb_code"].isin(DEFAULT_ZB)].assign(loss=loss).groupby("loan_id").agg(
        actual_loss=("loss", "sum"), zb_upb=("zb_upb", lambda s: pd.to_numeric(s, errors="coerce").max()))
    return out.join(zb, how="left")


def main():
    frames, report = [], {}
    for y in sorted(int(f.stem[-4:]) for f in RAW.glob("sample_orig_*.txt")):
        o, oc = load_orig(y), outcomes(y)
        df = o.merge(oc, left_on="loan_id", right_index=True, how="left", validate="1:1")
        missing_perf = int(df["default24"].isna().sum())
        df[["default24", "default24_strict", "ever_30dpd24", "prepaid24", "liquidated", "ever_relief"]] = \
            df[["default24", "default24_strict", "ever_30dpd24", "prepaid24", "liquidated", "ever_relief"]].fillna(False)
        # 24개월을 다 지켜봤거나(나이 ≥ 24), 그 전에 종료(상환·부도)된 대출만 결과가 확정됨
        df["observed"] = (df["max_age"] >= WINDOW) | df["prepaid24"] | df["default24"]
        frames.append(df)
        report[y] = {
            "loans": int(len(df)), "missing_perf": missing_perf, "observed": int(df["observed"].sum()),
            "default24": round(float(df.loc[df.observed, "default24"].mean()), 5),
            "default24_strict": round(float(df.loc[df.observed, "default24_strict"].mean()), 5),
            "ever_relief": round(float(df["ever_relief"].mean()), 4),
            "liquidated_total": int(df["liquidated"].sum()),
            "fico_median": float(df["fico"].median()), "rate_median": float(df["rate"].median()),
            "dti_median": float(df["dti"].median()), "upb_median": float(df["upb"].median()),
        }
    loans = pd.concat(frames, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    loans.to_parquet(OUT / "freddie_loans.parquet", index=False)
    (OUT / "freddie_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(loans.shape)


if __name__ == "__main__":
    sys.exit(main())

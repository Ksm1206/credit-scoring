"""원본 데이터를 모델링 가능한 형태로 1차 정리한다.

- 타깃(default=1)을 통일된 이름 `target`으로 만든다.
- Lending Club은 대출 실행 *이후*에만 알 수 있는 변수(누수 변수)를 분리한다.
- 결측·이상치는 고치지 않고 플래그만 남긴다 (처리는 EDA 단계에서 결정).

실행: python scripts/prepare_data.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
report = {}


# ---------------------------------------------------------------- 1. GMSC
def prepare_gmsc():
    df = pd.read_csv(RAW / "gmsc" / "cs-training.csv", index_col=0)
    df = df.rename(columns={"SeriousDlqin2yrs": "target"})
    # 연체 횟수 96/98은 실제 횟수가 아닌 특수 코드로 알려져 있음 → 플래그
    late_cols = ["NumberOfTime30-59DaysPastDueNotWorse",
                 "NumberOfTime60-89DaysPastDueNotWorse", "NumberOfTimes90DaysLate"]
    df["flag_late_code_96_98"] = df[late_cols].isin([96, 98]).any(axis=1).astype(int)
    df["flag_age_zero"] = (df["age"] == 0).astype(int)
    df["flag_income_missing"] = df["MonthlyIncome"].isna().astype(int)
    df.to_csv(OUT / "gmsc_train.csv", index_label="id")
    return df


# ---------------------------------------------------------- 2. Lending Club
LC_ID = ["id", "member_id", "url", "policy_code"]
LC_TEXT = ["emp_title", "desc", "title"]
# 대출 실행 후에 생기는 정보 → 학습에 쓰면 성능이 과대평가됨
LC_LEAKAGE = ["funded_amnt_inv", "pymnt_plan", "out_prncp", "out_prncp_inv",
              "total_pymnt", "total_pymnt_inv", "total_rec_prncp", "total_rec_int",
              "total_rec_late_fee", "recoveries", "collection_recovery_fee",
              "last_pymnt_d", "last_pymnt_amnt", "next_pymnt_d", "last_credit_pull_d"]
# Lending Club 자체 심사모델의 산출물 → 벤치마크로만 쓰는 걸 권장
LC_LENDER_PRICING = ["int_rate", "grade", "sub_grade", "installment"]


def prepare_lending_club():
    df = pd.read_csv(RAW / "lending_club" / "LoanStats3a.csv", skiprows=1, low_memory=False)
    df = df[df["loan_amnt"].notna()].copy()          # 파일 하단 요약행 제거

    status = df["loan_status"].astype(str)
    df["meets_credit_policy"] = (~status.str.startswith("Does not meet")).astype(int)
    base = status.str.replace("Does not meet the credit policy. Status:", "", regex=False)
    df["target"] = base.map({"Fully Paid": 0, "Charged Off": 1, "Default": 1})
    status_counts = base.value_counts().to_dict()
    df = df[df["target"].notna()].copy()             # Current/Late 등 미확정 대출 제외
    df["target"] = df["target"].astype(int)

    # 문자열 → 숫자/날짜
    for c in ["int_rate", "revol_util"]:
        df[c] = df[c].astype(str).str.rstrip("%").replace("nan", np.nan).astype(float)
    df["term_months"] = df.pop("term").str.extract(r"(\d+)").astype(float)
    emp = df["emp_length"].astype(str)
    df["emp_length_years"] = np.where(emp.str.contains("10\\+"), 10,
                              np.where(emp.str.contains("< 1"), 0,
                                       pd.to_numeric(emp.str.extract(r"(\d+)")[0], errors="coerce")))
    df.loc[df["emp_length"].isna() | (emp == "n/a"), "emp_length_years"] = np.nan
    for c in ["issue_d", "earliest_cr_line", "last_pymnt_d", "next_pymnt_d", "last_credit_pull_d"]:
        df[c] = pd.to_datetime(df[c], format="%b-%Y", errors="coerce")
    df["credit_history_months"] = ((df["issue_d"] - df["earliest_cr_line"]).dt.days / 30.44).round()

    # 전부 비어있는 컬럼(2012년 이후 추가된 항목) 제거
    empty = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty)

    keep_out = set(LC_ID + LC_TEXT + LC_LEAKAGE + ["loan_status", "emp_length"])
    features = [c for c in df.columns if c not in keep_out and c != "target"]
    df.drop(columns=["url"]).to_csv(OUT / "lending_club_full.csv", index=False)
    df[["id"] + features + ["target"]].to_csv(OUT / "lending_club_model.csv", index=False)
    return df, status_counts, empty, features


# -------------------------------------------------------- 3. German Credit
GERMAN_COLS = ["checking_status", "duration_months", "credit_history", "purpose",
               "credit_amount", "savings_status", "employment_since", "installment_rate_pct",
               "personal_status_sex", "other_debtors", "residence_since", "property",
               "age", "other_installment_plans", "housing", "existing_credits", "job",
               "num_dependents", "telephone", "foreign_worker", "class"]
GERMAN_CODES = {
    "A11": "< 0 DM", "A12": "0-200 DM", "A13": ">= 200 DM", "A14": "no checking account",
    "A30": "no credits / all paid", "A31": "all paid at this bank", "A32": "existing paid duly",
    "A33": "delay in past", "A34": "critical account",
    "A40": "car (new)", "A41": "car (used)", "A42": "furniture/equipment", "A43": "radio/TV",
    "A44": "appliances", "A45": "repairs", "A46": "education", "A47": "vacation",
    "A48": "retraining", "A49": "business", "A410": "others",
    "A61": "< 100 DM", "A62": "100-500 DM", "A63": "500-1000 DM", "A64": ">= 1000 DM", "A65": "unknown/none",
    "A71": "unemployed", "A72": "< 1 yr", "A73": "1-4 yrs", "A74": "4-7 yrs", "A75": ">= 7 yrs",
    "A91": "male: divorced/separated", "A92": "female: div/sep/married", "A93": "male: single",
    "A94": "male: married/widowed", "A95": "female: single",
    "A101": "none", "A102": "co-applicant", "A103": "guarantor",
    "A121": "real estate", "A122": "savings/life insurance", "A123": "car or other", "A124": "unknown/none",
    "A141": "bank", "A142": "stores", "A143": "none",
    "A151": "rent", "A152": "own", "A153": "for free",
    "A171": "unemployed/unskilled non-resident", "A172": "unskilled resident",
    "A173": "skilled employee", "A174": "management/self-employed/highly qualified",
    "A191": "none", "A192": "yes", "A201": "yes", "A202": "no",
}


def prepare_german():
    df = pd.read_csv(RAW / "german_credit" / "german.data", sep=" ", header=None, names=GERMAN_COLS)
    obj = df.select_dtypes(include=["object", "string"]).columns
    df[obj] = df[obj].apply(lambda s: s.map(GERMAN_CODES).fillna(s))
    df["target"] = (df.pop("class") == 2).astype(int)   # 1=good, 2=bad
    df.to_csv(OUT / "german_credit.csv", index_label="id")
    return df


def summarize(name, df):
    miss = df.isna().mean().sort_values(ascending=False)
    return {"rows": int(len(df)), "cols": int(df.shape[1]),
            "default_rate": round(float(df["target"].mean()), 4),
            "top_missing": {k: round(float(v), 4) for k, v in miss[miss > 0].head(8).items()}}


if __name__ == "__main__":
    g = prepare_gmsc()
    report["gmsc"] = summarize("gmsc", g)
    report["gmsc"]["flags"] = {c: int(g[c].sum()) for c in g.columns if c.startswith("flag_")}

    lc, status_counts, empty, feats = prepare_lending_club()
    report["lending_club"] = summarize("lending_club", lc)
    report["lending_club"].update({
        "raw_status_counts": status_counts, "dropped_empty_cols": len(empty),
        "model_features": len(feats), "leakage_cols_excluded": LC_LEAKAGE,
        "issue_period": [str(lc["issue_d"].min().date()), str(lc["issue_d"].max().date())],
        "default_rate_by_policy": lc.groupby("meets_credit_policy")["target"].mean().round(4).to_dict(),
    })

    report["german_credit"] = summarize("german", prepare_german())

    (OUT / "data_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

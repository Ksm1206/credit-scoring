"""앱 A/B 실험 분석: 기본형(A) vs 코칭형(B)

README "앱 A/B 실험 설계"의 판정을 실제 로그로 내립니다.

순서
1. 데이터 점검: 테스트 트래픽 제외, 중복 이벤트 확인, 실험군 배정 비율(SRM) 검정
2. 실험군별 퍼널: 방문 → 계산 → 결과 조회 → 피드백
3. 1차 지표: 결과를 본 사용자 중 '도움됐어요'를 누른 비율 (사용자 단위)
4. 판정: 빈도주의 검정 + 현재 표본으로 잡아낼 수 있는 최소 효과(MDE) + 베이지안 P(B > A)
   표본이 설계값(군당 약 1,400명)에 못 미치면 '판정 보류'와 그 근거를 함께 냅니다.

입력은 둘 중 하나입니다.
    python analysis/ab_experiment.py                      # DATABASE_URL(또는 로컬 SQLite)에서 직접 읽기
    python analysis/ab_experiment.py --csv events.csv     # Supabase/Neon에서 내보낸 events 테이블
옵션
    --exclude-users id1,id2     본인 테스트 등 내부 사용자 제외
    --since 2026-11-01          실험 시작일 이전 로그 제외 (배포 전 점검 로그 등)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]

DESIGN = {"baseline": 0.35, "mde": 0.05, "alpha": 0.05, "power": 0.80, "n_per_arm": 1400}
FUNNEL = ["page_view", "calc_submit", "result_view", "feedback"]

# DB에서 읽을 때 쓰는 쿼리. PostgreSQL과 SQLite 모두에서 돈다.
QUERY = """
SELECT event_id, ts, user_id, session_id, variant, event, props
FROM events
WHERE event IN ('page_view', 'calc_submit', 'result_view', 'tip_open',
                'feedback', 'share_click', 'human_review_request')
ORDER BY ts
"""


# ------------------------------------------------------------------ 입력
def load(csv: str | None) -> pd.DataFrame:
    if csv:
        df = pd.read_csv(csv)
    else:
        sys.path.insert(0, str(ROOT / "app"))
        import events  # noqa: E402
        df = pd.read_sql(QUERY, events.engine())
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["props"] = df["props"].fillna("{}").map(lambda s: json.loads(s) if isinstance(s, str) else (s or {}))
    return df


# ------------------------------------------------------------------ 1. 데이터 점검
def assigned_variant(uid: str) -> str:
    """앱(common.identify)과 같은 규칙으로 배정군을 다시 계산한다."""
    import hashlib
    return "A" if int(hashlib.md5(uid.encode()).hexdigest(), 16) % 2 == 0 else "B"


def quality(df: pd.DataFrame, exclude: set[str], since: str | None):
    report = {"events_raw": len(df), "users_raw": df.user_id.nunique()}
    if since:
        df = df[df.ts >= pd.Timestamp(since, tz="UTC")]
    df = df[~df.user_id.isin(exclude)]
    report["events_after_filter"] = len(df)

    # 같은 계산 결과에 피드백이 두 번 찍히는 경우(재실행 등)는 첫 건만 남긴다
    calc = df.props.map(lambda p: p.get("calc_id"))
    dup = df.assign(calc_id=calc).duplicated(["user_id", "event", "calc_id"]) & calc.notna() \
        & df.event.isin(["feedback", "result_view"])
    report["duplicate_events_removed"] = int(dup.sum())
    df = df[~dup]

    # 배정 규칙 위반: 로그의 variant가 해시 규칙과 다르면 배정 로직이나 로깅에 문제가 있다는 뜻
    mismatch = df.user_id.map(assigned_variant) != df.variant
    report["variant_mismatch_events"] = int(mismatch.sum())

    # 한 사용자가 두 군에 모두 찍힌 경우
    multi = df.groupby("user_id").variant.nunique()
    report["users_in_both_arms"] = int((multi > 1).sum())

    # SRM: 방문자가 50:50으로 나뉘었는가
    users = df.groupby("variant").user_id.nunique().reindex(["A", "B"], fill_value=0)
    n = users.sum()
    if n > 0:
        chi = stats.chisquare(users.values, [n / 2, n / 2])
        report["srm_users"] = users.to_dict()
        report["srm_p"] = float(chi.pvalue)
    report["users_clean"] = int(df.user_id.nunique())
    return df, report


# ------------------------------------------------------------------ 2. 퍼널
def funnel(df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for v, g in df.groupby("variant"):
        counts = [g.loc[g.event == e, "user_id"].nunique() for e in FUNNEL]
        helpful = g[(g.event == "feedback") & g.props.map(lambda p: p.get("helpful") is True)].user_id.nunique()
        rows[v] = counts + [helpful]
    t = pd.DataFrame(rows, index=["방문", "계산", "결과 조회", "피드백 응답", "도움됐어요"]).T
    t["계산률"] = t["계산"] / t["방문"]
    t["피드백 응답률"] = t["피드백 응답"] / t["결과 조회"]
    return t


# ------------------------------------------------------------------ 3~4. 1차 지표와 판정
def primary(df: pd.DataFrame) -> pd.DataFrame:
    """사용자 단위: 결과를 한 번이라도 본 사용자 중, 첫 피드백이 '도움됐어요'인 비율.

    한 사람이 여러 번 계산하면 관측치가 서로 독립이 아니므로 사람당 1건으로 줄인다.
    피드백을 안 누른 사람은 '도움됐어요'가 아닌 것으로 센다(설계의 분모 = 결과 조회자).
    """
    viewers = df[df.event == "result_view"].groupby("user_id").variant.first()
    fb = (df[df.event == "feedback"].sort_values("ts").groupby("user_id").props.first()
            .map(lambda p: p.get("helpful") is True))
    u = viewers.to_frame("variant").join(fb.rename("helpful")).fillna({"helpful": False})
    return u.groupby("variant").helpful.agg(n="size", x="sum").reindex(["A", "B"], fill_value=0)


def newcombe_ci(x1, n1, x2, n2, alpha=0.05):
    """두 비율 차이(p2 - p1)의 Newcombe 신뢰구간. 표본이 작아도 범위를 벗어나지 않는다."""
    def wilson(x, n):
        if n == 0:
            return 0.0, 1.0
        lo, hi = stats.binomtest(int(x), int(n)).proportion_ci(1 - alpha, method="wilson")
        return lo, hi
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    d = p2 - p1
    return d - np.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2), d + np.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)


def mde_at(n_per_arm, p=DESIGN["baseline"], alpha=DESIGN["alpha"], power=DESIGN["power"]):
    """군당 n명으로 검정력 80%를 내는 최소 효과(절대 %p)."""
    if n_per_arm <= 0:
        return np.nan
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return z * np.sqrt(2 * p * (1 - p) / n_per_arm)


def decide(t: pd.DataFrame, seed: int = 7) -> dict:
    (n1, x1), (n2, x2) = t.loc["A", ["n", "x"]].astype(int), t.loc["B", ["n", "x"]].astype(int)
    out = {"A": f"{x1}/{n1}", "B": f"{x2}/{n2}"}
    if min(n1, n2) == 0:
        out["판정"] = "판정 불가: 한 실험군에 결과 조회자가 없음"
        return out
    p1, p2 = x1 / n1, x2 / n2
    table = np.array([[x1, n1 - x1], [x2, n2 - x2]])
    # 기대도수가 5 미만인 칸이 있으면 카이제곱 대신 Fisher 정확검정
    expected = stats.contingency.expected_freq(table)
    test = "Fisher" if (expected < 5).any() else "카이제곱"
    p = stats.fisher_exact(table).pvalue if test == "Fisher" else stats.chi2_contingency(table, correction=False).pvalue
    lo, hi = newcombe_ci(x1, n1, x2, n2)
    rng = np.random.default_rng(seed)
    a = rng.beta(1 + x1, 1 + n1 - x1, 200_000)
    b = rng.beta(1 + x2, 1 + n2 - x2, 200_000)
    n_min = min(n1, n2)
    out.update({
        "A 비율": p1, "B 비율": p2, "차이(B-A)": p2 - p1, "95% CI": (lo, hi),
        "검정": test, "p-value": p, "P(B > A)": float((b > a).mean()),
        "현재 표본의 MDE": mde_at(n_min), "설계 표본 대비": n_min / DESIGN["n_per_arm"],
    })
    if n_min < DESIGN["n_per_arm"]:
        out["판정"] = (f"판정 보류: 군당 {n_min}명으로는 {out['현재 표본의 MDE']:.0%}p보다 작은 차이를 놓칠 확률이 20%를 넘음. "
                      f"설계한 효과 {DESIGN['mde']:.0%}p를 보려면 군당 {DESIGN['n_per_arm']:,}명 필요")
    elif p < DESIGN["alpha"] and lo > 0:
        out["판정"] = "B안(코칭형) 채택"
    elif p < DESIGN["alpha"] and hi < 0:
        out["판정"] = "A안(기본형) 유지: B가 유의하게 낮음"
    else:
        out["판정"] = f"차이 없음: 신뢰구간 {lo:+.1%}~{hi:+.1%}에 설계 효과 {DESIGN['mde']:.0%}p 미만이 대부분"
    return out


# ------------------------------------------------------------------ 2차 지표
def secondary(df: pd.DataFrame) -> pd.DataFrame:
    viewers = df[df.event == "result_view"].groupby("variant").user_id.nunique()
    res = {}
    for e, name in [("share_click", "공유율"), ("human_review_request", "사람 심사 요청률"), ("tip_open", "팁 열람률(A만 해당)")]:
        res[name] = df[df.event == e].groupby("variant").user_id.nunique().reindex(viewers.index, fill_value=0) / viewers
    calc = df[df.event == "calc_submit"].groupby(["variant", "user_id"]).size()
    res["재계산률"] = (calc > 1).groupby("variant").mean()
    days = df.assign(d=df.ts.dt.date).groupby(["variant", "user_id"]).d.nunique()
    res["재방문율(2일 이상 방문)"] = (days > 1).groupby("variant").mean()
    return pd.DataFrame(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--exclude-users", default="")
    ap.add_argument("--since")
    a = ap.parse_args()

    df, q = quality(load(a.csv), {u for u in a.exclude_users.split(",") if u}, a.since)
    f, t = funnel(df), primary(df)
    d, s = decide(t), secondary(df)

    pd.set_option("display.width", 200)
    print("[1] 데이터 점검"); print(json.dumps(q, ensure_ascii=False, indent=2, default=str))
    print("\n[2] 실험군별 퍼널 (사용자 수)"); print(f.round(3).to_string())
    print("\n[3] 1차 지표: 결과 조회자 중 '도움됐어요' 비율"); print(t.to_string())
    print("\n[4] 판정")
    for k, v in d.items():
        if isinstance(v, tuple):
            v = f"{v[0]:+.1%} ~ {v[1]:+.1%}"
        elif isinstance(v, float):
            v = f"{v:.3f}" if k == "p-value" else f"{v:.1%}"
        print(f"  {k}: {v}")
    print("\n[5] 2차 지표"); print(s.round(3).to_string())

    out = ROOT / "reports" / "ab_experiment"
    out.mkdir(parents=True, exist_ok=True)
    f.to_csv(out / "funnel.csv", encoding="utf-8-sig")
    s.to_csv(out / "secondary.csv", encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps({"quality": q, "decision": d}, ensure_ascii=False,
                                                 indent=2, default=lambda o: list(o) if isinstance(o, tuple) else str(o)),
                                      encoding="utf-8")


if __name__ == "__main__":
    main()

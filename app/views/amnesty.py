"""③ 신용사면 시뮬레이터: 연체 기록을 지우면 누가 승인되고, 손실은 누가 떠안는가."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("amnesty")
A = cm.load_artifacts()
T = cm.score_table()
G, B = int(T.good.sum()), int(T.bad.sum())

st.title("🧽 신용사면 시뮬레이터")
with st.container(border=True):
    st.markdown(
        "**배경** 정부는 2025년 8월, 2020년~2025년 6월에 생긴 **5천만 원 이하 연체를 연말까지 모두 갚으면 연체 기록을 삭제**하는 "
        "신용사면을 발표했습니다. 대상은 약 **324만 명**으로 역대 최대 규모입니다. "
        f"(출처: {cm.source_link('amnesty')})\n\n"
        "**질문** 연체 기록이 지워지면 점수는 얼마나 오르고, 새로 승인되는 사람은 실제로 얼마나 갚을까요? "
        "그리고 정보가 사라진 만큼의 위험은 누가 떠안을까요?"
    )
    st.caption("※ 미국 데이터에 '연체 기록 삭제'라는 같은 구조의 정책을 적용한 시뮬레이션입니다. 한국 정책의 실제 효과 측정이 아닙니다. "
               "결과(2년 내 부도 여부)는 실제 관측값입니다.")

c1, c2, c3 = st.columns([2, 1, 1])
scope = c1.radio("삭제 범위", list(A["amnesty"]), format_func=lambda k: A["amnesty"][k]["label"], horizontal=True, index=1)
cutoff = c2.number_input("승인 기준점", 480, 620, cm.load_policy()["approve_cutoff"])
lgd = c3.number_input("손실률 LGD (%)", 20, 100, 60)
gain, loss = cm.unit_economics(10, lgd)

am = A["amnesty"][scope]
aff = pd.DataFrame(am["affected"], columns=["orig", "new", "target", "n"])
aff["good"] = aff.n.where(aff.target == 0, 0)
aff["bad"] = aff.n.where(aff.target == 1, 0)


def table_from(df, col):
    return df.groupby(col)[["good", "bad"]].sum().rename_axis("score").reset_index()


# 사면 전 = 원래 점수, 사면 후 = 대상자만 새 점수
orig_aff = table_from(aff, "orig")
new_aff = table_from(aff, "new")
unaff = T.set_index("score").sub(orig_aff.set_index("score"), fill_value=0).reset_index()
after = unaff.set_index("score").add(new_aff.set_index("score"), fill_value=0).reset_index()


def approved(t, c):
    r = t[t.score >= c]
    return r.good.sum(), r.bad.sum()


before = cm.portfolio(*approved(T, cutoff), G, B, gain, loss)
post = cm.portfolio(*approved(after, cutoff), G, B, gain, loss)
newly = aff[(aff.orig < cutoff) & (aff.new >= cutoff)]
n_new, bad_new = int(newly.n.sum()), int(newly.bad.sum())
n_aff = int(aff.n.sum())
avg_gain = float((aff.new - aff.orig).mul(aff.n).sum() / n_aff)
aff_bad = float(aff.bad.sum() / n_aff)

k = st.columns(4)
k[0].metric("사면 대상", f"{n_aff:,}명", f"신청자의 {cm.pct(n_aff / (G + B))}", delta_color="off")
k[1].metric("평균 점수 상승", f"+{avg_gain:.0f}점")
k[2].metric("새로 승인되는 사람", f"{n_new:,}명")
k[3].metric("그중 실제 부도율", cm.pct(bad_new / n_new) if n_new else "-",
            f"기존 승인자 {cm.pct(before['승인자 부도율'])}", delta_color="off")

if n_new:
    ratio = (bad_new / n_new) / before["승인자 부도율"]
    st.markdown(f"사면으로 새로 승인된 **{n_new:,}명 중 {bad_new:,}명({cm.pct(bad_new / n_new)})이 2년 안에 실제로 부도**를 냈습니다. "
                f"기존 승인자 부도율의 **{ratio:.1f}배**입니다. 반대로 보면 **{n_new - bad_new:,}명은 연체 기록 때문에 거절됐을 "
                f"정상 상환자**이고, 사면 덕분에 대출을 받게 됩니다.")

# ---------------------------------------------------------------- 점수 분포 변화
st.subheader("사면 대상자의 점수 분포 변화")
hist = pd.concat([
    aff.assign(score=aff.orig, 시점="사면 전")[["score", "n", "시점"]],
    aff.assign(score=aff.new, 시점="사면 후")[["score", "n", "시점"]],
])
hist["구간"] = (hist.score // 10) * 10
hist = hist.groupby(["구간", "시점"], as_index=False).n.sum()
ch = alt.Chart(hist).mark_bar(opacity=0.75).encode(
    x=alt.X("구간:O", title="점수 (10점 구간)"), y=alt.Y("n:Q", title="인원", stack=None),
    color=alt.Color("시점:N", scale=alt.Scale(domain=["사면 전", "사면 후"], range=["#8FB8B2", "#E4572E"]),
                    legend=alt.Legend(orient="top", title=None)),
    tooltip=["시점", "구간", "n"])
rule = alt.Chart(pd.DataFrame({"x": [(cutoff // 10) * 10]})).mark_rule(color="#15202B", strokeDash=[4, 3]).encode(x="x:O")
st.altair_chart((ch + rule).properties(height=260), width="stretch")
st.caption(f"점선 = 승인 기준점({cutoff}점). 대상자 전체의 실제 부도율은 {cm.pct(aff_bad)}로, 전체 평균 {cm.pct(B / (G + B))}의 "
           f"{aff_bad / (B / (G + B)):.1f}배입니다.")

# ---------------------------------------------------------------- 은행 영향
st.subheader("은행은 어떻게 반응할까")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**① 기준점을 그대로 두면**")
    st.dataframe(pd.DataFrame({
        "": ["승인율", "승인자 부도율", "신청 1억 원당 손익"],
        "사면 전": [cm.pct(before["승인율"]), cm.pct(before["승인자 부도율"]), cm.won(before["1인당 손익"])],
        "사면 후": [cm.pct(post["승인율"]), cm.pct(post["승인자 부도율"]), cm.won(post["1인당 손익"])],
    }), hide_index=True, width="stretch")

# 부도율을 사면 전 수준으로 되돌리려면 기준점을 얼마나 올려야 하나
target_br = before["승인자 부도율"]
new_cut = next((c for c in range(cutoff, 700) if cm.portfolio(*approved(after, c), G, B, gain, loss)["승인자 부도율"] <= target_br), None)
with c2:
    st.markdown("**② 부도율을 원래대로 지키려고 기준점을 올리면**")
    if new_cut is None or new_cut == cutoff:
        st.write("기준점을 올리지 않아도 부도율이 유지됩니다.")
    else:
        lost_good = int(unaff[(unaff.score >= cutoff) & (unaff.score < new_cut)].good.sum())
        adj = cm.portfolio(*approved(after, new_cut), G, B, gain, loss)
        st.dataframe(pd.DataFrame({
            "": ["새 기준점", "승인율", "사면과 무관한 정상 상환자 추가 거절"],
            "값": [f"{new_cut}점 (+{new_cut - cutoff})", cm.pct(adj["승인율"]), f"{lost_good:,}명"],
        }), hide_index=True, width="stretch")
        st.caption("연체 정보가 사라진 만큼 은행이 기준을 올리면, **사면 대상이 아닌 정상 상환자**가 대신 거절될 수 있습니다.")

# ---------------------------------------------------------------- 연령대
st.subheader("누가 혜택을 받나: 연령대별 사면 대상")
ba = pd.DataFrame(am["by_age"], columns=["연령대", "target", "n"])
ba = ba.pivot_table(index="연령대", columns="target", values="n", fill_value=0).rename(columns={0: "정상", 1: "부도"})
ba = ba.reindex(A["meta"]["age_groups"]).fillna(0)
ba["대상자"] = ba.sum(axis=1)
ba["실제 부도율"] = ba["부도"] / ba["대상자"]
chart = alt.Chart(ba.reset_index()).mark_bar(color="#1F7A73").encode(
    x=alt.X("연령대:N", sort=A["meta"]["age_groups"]), y=alt.Y("대상자:Q"),
    tooltip=["연령대", "대상자", alt.Tooltip("실제 부도율:Q", format=".1%")])
c1, c2 = st.columns([3, 2])
c1.altair_chart(chart.properties(height=220), width="stretch")
c2.dataframe(ba[["대상자", "실제 부도율"]].style.format({"대상자": "{:,.0f}", "실제 부도율": "{:.1%}"}),
             width="stretch")

with st.expander("📌 정리: 신용사면의 두 얼굴"):
    st.markdown(
        f"- **재기 지원**: 기준점 {cutoff}점 기준으로 연체 기록 때문에 거절됐을 정상 상환자 **{n_new - bad_new:,}명**이 대출을 받게 됩니다.\n"
        f"- **위험 전가**: 새로 승인된 사람의 부도율은 기존 승인자의 약 {((bad_new / n_new) / target_br) if n_new else 0:.1f}배입니다. "
        "은행이 손실을 막으려 기준을 올리면 사면과 무관한 정상 상환자가 대신 거절되고, 금리가 오를 수도 있습니다.\n"
        "- **정책 시사점**: 기록을 모두 지우기보다 '상환 완료' 사실을 남겨 **성실 상환 이력을 가점으로 반영**하는 방식이 "
        "정보 손실을 줄이면서 재기를 돕는 대안이 될 수 있습니다."
    )
cm.sidebar_note()

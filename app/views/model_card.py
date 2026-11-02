"""⑤ 모델 카드: AI 기본법(고영향 AI) 의무에 맞춘 모델 설명·검증·위험관리 문서."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("model_card")
A = cm.load_artifacts()
MC = A["model_card"]
CARD = cm.load_card()

st.title("🗂️ 모델 카드")
st.caption("신용평가 모델의 목적, 데이터, 성능, 한계, 위험관리 방법을 한곳에 공개하는 문서입니다.")

with st.container(border=True):
    st.markdown(
        "**왜 필요한가** 2026년 1월 시행된 AI 기본법에서 대출심사·신용평가처럼 국민의 신용도에 중대한 영향을 주는 AI는 "
        "**고영향 AI**로 분류됩니다. 사업자는 위험관리 방안, 학습데이터·알고리즘 설명, 이용자 보호, 사람의 관리·감독 체계를 갖춰야 합니다. "
        f"(출처: {cm.source_link('aiact')})"
    )

st.subheader("고영향 AI 의무와 이 프로젝트의 대응")
st.markdown(
    "| 의무 | 이 프로젝트의 대응 | 관련 화면 |\n|---|---|---|\n"
    "| **위험관리 방안** | 분포 안정성(PSI·CSI) 점검, 연령대별 공정성 점검, 정책 변화(신용사면) 영향 시뮬레이션 | 모델 카드 · 청년 공정성 · 신용사면 |\n"
    "| **설명 가능성** | 구간별 점수표 전체 공개, 개인별 주요 감점 사유 Top 3 제공 | 모델 카드 · 내 신용점수 |\n"
    "| **이용자 보호** | 입력 원본 미저장(점수·등급만 익명 기록), 학습용 모델 고지 | 내 신용점수 |\n"
    "| **사람의 관리·감독** | '사람 심사 요청' 기능, 비교용 챌린저 모델(LightGBM) 병행 모니터링 | 내 신용점수 · 승인 정책 |"
)

c1, c2 = st.columns(2)
with c1:
    st.subheader("모델 개요")
    st.markdown(
        f"- **목적**: 개인 대출 신청자의 2년 내 90일 이상 연체 확률 예측\n"
        f"- **구조**: WoE 로지스틱 스코어카드, {len(CARD['features'])}개 변수\n"
        f"- **점수 체계**: 600점 = 정상:부도 50:1, 20점마다 odds 2배\n"
        f"- **데이터**: {cm.source_link('data')}\n"
        f"- **분할**: 학습 {MC['n_train']:,} · 검증 {MC['n_valid']:,} · 테스트 {A['meta']['n_test']:,}명"
    )
with c2:
    st.subheader("성능 (테스트셋)")
    perf = pd.DataFrame({"AUC": MC["auc"]}).assign(KS=pd.Series(MC["ks"]))
    st.dataframe(perf.astype(float).style.format("{:.3f}", na_rep="-"), width="stretch")
    st.metric("점수 분포 안정성 PSI (학습→테스트)", f"{MC['psi']:.4f}", "안정 (0.1 미만)", delta_color="off")

st.subheader("변수별 예측력(IV)과 분포 안정성(CSI)")
fv = pd.DataFrame({"변수": [CARD["features"][f]["label_ko"] for f in MC["iv"]],
                   "IV": list(MC["iv"].values()), "CSI": [MC["csi"][f] for f in MC["iv"]]})
fv["판정"] = fv["CSI"].map(lambda v: "안정" if v < 0.1 else ("점검" if v < 0.25 else "재학습 검토"))
c1, c2 = st.columns([3, 2])
c1.altair_chart(alt.Chart(fv).mark_bar(color="#1F7A73").encode(
    x=alt.X("IV:Q"), y=alt.Y("변수:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
    tooltip=["변수", alt.Tooltip("IV:Q", format=".3f")]
).properties(height=280, title="IV (0.1 이상 중간, 0.3 이상 강함)"), width="stretch")
c2.markdown("**CSI** (학습 → 테스트 분포 변화)")
c2.dataframe(fv[["변수", "CSI", "판정"]].sort_values("CSI", ascending=False).style.format({"CSI": "{:.4f}"}),
             hide_index=True, width="stretch")
st.caption("운영 중에는 월별 신청자 분포로 PSI·CSI를 다시 계산해, 0.1을 넘으면 원인을 점검하고 0.25를 넘으면 재학습을 검토합니다.")

st.subheader("점수표 전체")
f = st.selectbox("변수 선택", list(CARD["features"]), format_func=lambda k: CARD["features"][k]["label_ko"])
spec = CARD["features"][f]
bt = pd.DataFrame(spec["bins"])
bt["점수"] = bt["bin"].map(spec["points"])
st.dataframe(bt.rename(columns={"bin": "구간", "count": "학습 인원", "bad": "부도", "bad_rate": "부도율", "woe": "WoE"})
             [["구간", "학습 인원", "부도율", "WoE", "점수"]].style.format({"부도율": "{:.1%}", "WoE": "{:.3f}", "학습 인원": "{:,}"}),
             hide_index=True, width="stretch")

st.subheader("알려진 한계")
st.markdown(
    "- 미국 2011년 데이터로 학습해 한국 신용시장과 다릅니다. 실제 심사에 쓸 수 없습니다.\n"
    "- 대출금액·금리 정보가 없어 손익은 동일 금액 가정입니다.\n"
    "- 거절된 사람의 실제 결과를 모르는 상태로 학습했습니다(Reject Inference 미적용).\n"
    "- 일부 변수(DTI, 소득)의 구간 점수가 단조롭지 않습니다. 원천 데이터 기록 방식 문제로 추정합니다.\n"
    "- 연령 변수 사용에 따른 공정성 쟁점은 '청년 공정성' 화면에서 정량 점검합니다."
)
cm.sidebar_note()

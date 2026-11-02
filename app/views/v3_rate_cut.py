"""v3 · 금리인하요구권: 신청 대상인지, 얼마나 아낄 수 있는지, 어떻게 신청하는지."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import common as cm  # noqa: E402

cm.identify()
cm.page_view("v3_rate_cut")
R = cm.load_rules()
RC = R["rate_cut_right"]
fc = cm.fc

st.title("📉 금리인하요구권 진단")
st.caption("대출을 받은 뒤 **취업·승진·소득 증가·신용점수 상승**이 있었다면 금융회사에 금리를 낮춰 달라고 요구할 수 있는 법적 권리입니다. "
           f"2026년 상반기 은행권에서만 {RC['applications_h1_2026'] / 1e4:,.0f}만 건이 신청됐습니다.")

with st.container(border=True):
    st.markdown("**대출 받은 뒤에 이런 변화가 있었나요?** (해당하는 것을 모두 선택)")
    cols = st.columns(2)
    picked = [t for i, t in enumerate(RC["triggers"]) if cols[i % 2].checkbox(t, key=f"rc_{i}")]
    st.markdown("**대출 정보**")
    c1, c2, c3, c4 = st.columns(4)
    bal = c1.number_input("남은 원금 (만 원)", 100, 200000, 5000, step=100) * 1e4
    rate = c2.number_input("지금 금리 (연 %)", 0.5, 20.0, 6.0, step=0.1, format="%.2f")
    remain = c3.number_input("남은 기간 (개월)", 1, 480, 36)
    method = c4.selectbox("상환 방식", fc.METHODS, index=2)
    special = st.checkbox("정책자금 대출(디딤돌·버팀목·햇살론 등)이거나 아파트 집단대출(중도금 등)이다",
                          help="이런 상품은 금리가 정책적으로 정해져 금리인하요구 대상이 아닐 수 있습니다.")

cut = st.slider("예상 인하폭 (%p)", 0.1, 2.0, 0.3, step=0.05,
                help="수용될 때 인하폭은 사람마다 다릅니다. 보수적으로 0.2~0.5%p로 가정해 보세요.")
sv = fc.rate_cut_saving(bal, rate, cut, remain, method)

st.divider()
if special:
    st.warning("정책자금·집단대출은 금리인하요구 대상이 아닐 수 있습니다. 신청 전에 금융회사에 대상 여부를 먼저 물어보세요.")
elif picked:
    st.success(f"**신청해 볼 만합니다.** 선택한 변화 {len(picked)}가지는 대표적인 신청 사유입니다.")
else:
    st.info("아직 해당하는 변화가 없다면 지금은 수용 가능성이 낮습니다. 신용점수를 올린 뒤 다시 확인해 보세요. "
            "('내 신용점수' 화면에서 점수 올리는 방법을 볼 수 있어요)")

k = st.columns(3)
k[0].metric(f"{cut:.2f}%p 인하 시 첫 1년 절약", cm.krw(sv["first_year"]))
k[1].metric("남은 기간 전체 절약", cm.krw(sv["total"]))
k[2].metric("은행권 평균 수용률", f"{RC['acceptance_rate_banks']}%", f"인터넷은행 {RC['acceptance_rate_internet_banks']}%", delta_color="off",
            help=f"{RC['acceptance_rate_period']} 기준. 신청이 크게 늘면서 수용률은 낮아졌습니다.")
st.caption("신청은 무료이고 거절돼도 불이익이 없습니다. 수용률이 낮더라도 기대 이익이 비용(0원)보다 크니 해당되면 신청하는 편이 낫습니다.")

c1, c2 = st.columns([3, 2])
with c1:
    st.subheader("신청 방법")
    st.markdown(
        "1. **자동 신청(가장 쉬움)**: 2026년 2월부터 마이데이터 앱(약 70곳)에서 한 번 동의하면, 신용 변동이 생길 때마다 "
        "앱이 대신 금리인하를 신청해 줍니다. 쓰고 있는 금융 앱의 '금리인하요구' 메뉴를 확인하세요.\n"
        "2. **직접 신청**: 대출받은 은행 앱·홈페이지·창구에서 '금리인하요구권'을 신청합니다. 재직·소득 증빙(건강보험 자격득실, 원천징수영수증 등)을 준비하면 좋습니다.\n"
        "3. **결과 통지**: 금융회사는 접수 후 일정 기간 안에 수용 여부와 사유를 알려줘야 합니다. 거절되면 사유를 확인하고, 상황이 더 좋아진 뒤 다시 신청할 수 있습니다."
    )
with c2:
    st.subheader("인하폭별 절약액")
    rows = [{"인하폭": f"−{c:.2f}%p", "첫 1년": cm.krw(fc.rate_cut_saving(bal, rate, c, remain, method)["first_year"]),
             "전체": cm.krw(fc.rate_cut_saving(bal, rate, c, remain, method)["total"])} for c in (0.1, 0.2, 0.3, 0.5, 1.0)]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

if picked and not special and st.button("✅ 신청하러 갈게요"):
    cm.track("rate_cut_intent", n_triggers=len(picked), cut=cut)
    st.toast("좋아요! 대출받은 금융회사 앱의 '금리인하요구' 메뉴에서 신청하세요.")
cm.rule_sources("rate_cut_right", "금리인하요구권 통계·제도 근거")
cm.v3_disclaimer()
cm.sidebar_note_v3()

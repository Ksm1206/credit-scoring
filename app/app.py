"""신용평가 서비스 (Streamlit 멀티페이지).

실행: streamlit run app/app.py
"""
from pathlib import Path

import streamlit as st

V = Path(__file__).resolve().parent / "views"
st.set_page_config(page_title="생활 금융 도우미", page_icon="💡", layout="wide")

pages = {
    "생활 금융 도우미": [
        st.Page(V / "v3_benefits.py", title="내 금융 혜택 찾기", icon="💡", default=True),
        st.Page(V / "v3_refinance.py", title="대출 갈아타기 계산기", icon="🔄"),
        st.Page(V / "v3_rate_cut.py", title="금리인하요구권 진단", icon="📉"),
        st.Page(V / "v3_mortgage.py", title="주담대 한도 계산기", icon="🏠"),
        st.Page(V / "v3_relief.py", title="서민금융·채무조정 길잡이", icon="🤝"),
    ],
    "내 신용": [st.Page(V / "my_score.py", title="내 신용점수", icon="📊")],
    "금융사·정책 분석": [
        st.Page(V / "mortgage_us.py", title="미국 주담대 분석 (2021~23)", icon="🇺🇸"),
        st.Page(V / "policy.py", title="승인 정책 시뮬레이터", icon="🏦"),
        st.Page(V / "amnesty.py", title="신용사면 시뮬레이터", icon="🧽"),
        st.Page(V / "fairness.py", title="청년 공정성 점검", icon="⚖️"),
    ],
    "모델 거버넌스": [st.Page(V / "model_card.py", title="모델 카드", icon="🗂️")],
}
st.navigation(pages).run()

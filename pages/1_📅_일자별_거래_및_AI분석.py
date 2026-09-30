import os
from pathlib import Path
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from src.storage import DEFAULT_DB_PATH, DEFAULT_PARQUET_PATH
from src.dashboard.queries import (
    get_available_dates,
    get_daily_market_metrics,
    get_daily_deals_table
)
from src.analyzer import get_or_create_daily_analysis

load_dotenv()

st.set_page_config(
    page_title="일자별 실거래 & AI 마켓 브리핑",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 스타일 적용
st.markdown("""
<style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .report-box {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 24px;
        margin-top: 10px;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }
    .badge-cache {
        background-color: #ecfdf5;
        color: #065f46;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid #a7f3d0;
    }
    .badge-fresh {
        background-color: #eff6ff;
        color: #1e40af;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid #bfdbfe;
    }
</style>
""", unsafe_allow_html=True)

# 1. Parquet 데이터 확인
parquet_path = DEFAULT_PARQUET_PATH
db_path = DEFAULT_DB_PATH

if not Path(parquet_path).exists():
    st.error(f"실거래가 데이터 파일(`{parquet_path}`)을 찾을 수 없습니다. 먼저 수집기를 실행해 주세요.")
    st.stop()

# 2. 일자 목록 로드
available_dates = get_available_dates(parquet_path)
if not available_dates:
    st.warning("수집된 실거래 데이터 일자가 없습니다.")
    st.stop()

# 사이드바 설정
st.sidebar.header("📅 일자 및 필터 선택")
selected_date = st.sidebar.selectbox("조회 일자", options=available_dates, index=0)

sido_options = ["전체", "서울특별시", "경기도", "인천광역시", "부산광역시", "대구광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도"]
selected_sido = st.sidebar.selectbox("지역(시·도) 필터", options=sido_options, index=0)

force_refresh = st.sidebar.button("🔄 AI 분석 새로고침", help="이미 저장된 캐시를 무시하고 Gemini API를 다시 호출하여 새로운 분석을 생성합니다.")

st.sidebar.markdown("---")
st.sidebar.info("""
**💡 AI 마켓 브리핑 안내**
- 최초 1회 생성된 애널리스트 리포트는 **SQLite DB**에 영구 저장됩니다.
- 동일한 날짜를 다시 조회할 때는 API 재호출 없이 **저장된 리포트**를 즉시 불러옵니다.
""")

# 3. 메인 콘텐츠
st.title(f"📅 [{selected_date}] 일일 실거래 마켓 브리핑")
st.caption(f"기준 일자: {selected_date} | 데이터 소스: 국토교통부 아파트매매 실거래가")

# 핵심 지표 집계
metrics = get_daily_market_metrics(parquet_path, selected_date)

# KPI 4열 카드
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("총 거래 건수", f"{metrics['deal_count']:,} 건")
with col2:
    st.metric("평균 거래금액", f"{metrics['avg_amount']:,} 만원")
with col3:
    st.metric("평균 평당가", f"{metrics['avg_pyeong_price']:,} 만원/평")
with col4:
    max_title = metrics['top3_deals'][0]['apt_name'] if metrics['top3_deals'] else "-"
    st.metric("당일 최고가", f"{metrics['max_amount']:,} 만원", help=f"최고가 단지: {max_title}")

st.markdown("---")

# 4. 🤖 AI 부동산 애널리스트 리포트 섹션
gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

col_rep_title, col_rep_btn = st.columns([3, 1])
with col_rep_title:
    st.subheader("🤖 부동산 전문 수석 애널리스트 마켓 리포트")
with col_rep_btn:
    main_refresh = st.button("🔄 AI 분석 다시 생성하기", key="main_refresh_btn", help="기존 저장된 내용을 지우고 Gemini API로 전체 리포트를 처음부터 다시 작성합니다.", use_container_width=True)

should_refresh = force_refresh or main_refresh

if not gemini_key:
    st.warning("⚠️ `.env` 파일에 `GEMINI_API_KEY`가 설정되어 있지 않습니다. 키를 등록하시면 인공지능 애널리스트의 날카로운 일일 분석 리포트가 자동으로 생성됩니다.")
    st.markdown("""
    ```ini
    # .env 파일에 아래 설정을 추가해 주세요
    GEMINI_API_KEY=your_google_gemini_api_key_here
    ```
    """)
else:
    with st.spinner("AI 부동산 애널리스트가 당일 시장 데이터를 심층 분석 중입니다..."):
        analysis_data, is_cached = get_or_create_daily_analysis(
            deal_date=selected_date,
            parquet_path=parquet_path,
            db_path=db_path,
            api_key=gemini_key,
            force_refresh=should_refresh
        )

    # 뱃지 및 생성 정보 표시
    badge_html = (
        '<span class="badge-cache">💾 SQLite DB 캐시에서 불러옴 (API 호출 0회)</span>'
        if is_cached else
        '<span class="badge-fresh">✨ Gemini 3.5 Flash 신규 생성 완료 (DB 영구 저장됨)</span>'
    )
    created_at = analysis_data.get("created_at", "")
    info_text = f"분석 일시: {created_at}" if created_at else ""

    st.markdown(f"{badge_html} &nbsp; <small style='color: #64748b;'>{info_text}</small>", unsafe_allow_html=True)
    
    # 마크다운 박스 렌더링
    st.markdown(f"""
    <div class="report-box">
    {analysis_data.get('summary_markdown', '분석 내용이 없습니다.')}
    </div>
    """, unsafe_allow_html=True)

# 5. 📋 당일 상세 거래 내역 테이블
st.subheader(f"📋 [{selected_date}] 전국 아파트 실거래 상세 내역")

deals_df = get_daily_deals_table(parquet_path, selected_date, sido=selected_sido)

if deals_df.empty:
    st.info("선택한 조건에 해당하는 실거래 내역이 없습니다.")
else:
    # 컬럼 포맷팅
    display_df = deals_df.copy()
    display_df = display_df.rename(columns={
        "sido_name": "시도",
        "sgg_name": "시군구",
        "umd_nm": "법정동",
        "apt_name": "단지명",
        "exclusive_area": "전용면적(㎡)",
        "pyeong": "평형",
        "floor": "층",
        "deal_amount": "거래금액(만원)",
        "price_per_pyeong": "평당가격(만원)",
        "build_year": "건축년도"
    })
    
    # 상단 요약 및 다운로드 버튼
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.caption(f"조회된 거래: 총 **{len(display_df):,}** 건 (거래금액 높은 순)")
    with col_t2:
        csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 CSV 다운로드",
            data=csv_data,
            file_name=f"{selected_date}_{selected_sido}_아파트실거래.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.dataframe(
        display_df[[
            "시도", "시군구", "법정동", "단지명", "평형", "전용면적(㎡)", "층",
            "거래금액(만원)", "평당가격(만원)", "건축년도"
        ]],
        use_container_width=True,
        hide_index=True
    )

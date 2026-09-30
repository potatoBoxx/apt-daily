import os
from datetime import datetime
from pathlib import Path
import streamlit as st
import pandas as pd

from src.dashboard.queries import (
    get_kpis, get_daily_trend, get_top_regions, get_price_distribution,
    get_top_deals, get_filtered_deals, get_sgg_options
)
from src.dashboard.components import (
    render_kpi_cards, create_trend_chart, create_region_bar_chart, create_price_box_plot, format_krw_amount
)
from src.collector import AptTradeCollector
from src.storage import DEFAULT_PARQUET_PATH, DEFAULT_DB_PATH

# 페이지 기본 설정
st.set_page_config(
    page_title="전국 아파트 실거래가 일일 대시보드",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 스타일링 CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-container {
        background-color: #F9FAFB;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #E5E7EB;
    }
    .stDownloadButton button {
        background-color: #2563EB;
        color: white;
        font-weight: 600;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# 헤더 영역
st.markdown('<div class="main-header">🏢 전국 아파트 매매 실거래가 대시보드</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">국토교통부 OpenAPI 기반 최근 1주일간 전국 실거래 동향 (Parquet + SQLite + DuckDB 초고속 OLAP 분석)</div>',
    unsafe_allow_html=True
)

parquet_path = DEFAULT_PARQUET_PATH

# 데이터 파일 존재 여부 검사
if not Path(parquet_path).exists():
    st.warning("⚠️ 아직 실거래가 데이터 파일이 생성되지 않았습니다.")
    st.info("공공데이터포털 API 키가 없어도 아래 버튼을 누르면 테스트용 Mock 샘플 데이터(500건)가 즉시 생성됩니다.")
    if st.button("🚀 샘플 실거래가 데이터(500건) 생성하기", type="primary"):
        with st.spinner("샘플 실거래가 데이터를 생성 중입니다..."):
            collector = AptTradeCollector()
            collector.collect_all(days=7)
        st.success("데이터 생성이 완료되었습니다! 페이지를 새로고침합니다.")
        st.rerun()
    st.stop()

# 사이드바 필터 구성
st.sidebar.header("🔍 검색 및 필터 옵션")

# 1. 시도 목록 가져오기
SIDO_LIST = [
    "전체", "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도"
]
selected_sido = st.sidebar.selectbox("📍 시/도 선택", SIDO_LIST, index=0)

# 2. 시군구 다중 선택
sgg_options = get_sgg_options(parquet_path, sido=selected_sido)
selected_sgg = st.sidebar.multiselect("🏙️ 시/군/구 선택 (선택 안하면 전체)", sgg_options)

# 3. 평형대 구분
PYEONG_OPTIONS = ["전체", "소형 (59㎡ 미만)", "중소형 (59~84㎡ 미만)", "국민평형 (84~102㎡ 미만)", "대형 (102㎡ 이상)"]
selected_pyeong = st.sidebar.selectbox("📐 전용면적(평형) 구분", PYEONG_OPTIONS, index=0)

# 4. 금액 범위 슬라이더
amount_range = st.sidebar.slider(
    "💵 거래금액 범위 (만원)",
    min_value=0,
    max_value=500000,
    value=(0, 500000),
    step=5000,
    format="%d만원"
)
min_amount, max_amount = amount_range

# 사이드바 하단 정보
st.sidebar.markdown("---")
st.sidebar.caption(f"🕒 대시보드 기준일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
if st.sidebar.button("🔄 데이터 다시 수집 (Mock 실행)"):
    with st.spinner("데이터를 새로 수집 중입니다..."):
        collector = AptTradeCollector()
        collector.collect_all(days=7)
    st.success("데이터 갱신 완료!")
    st.rerun()

# 1. KPI 지표 카드 렌더링
kpis = get_kpis(
    parquet_path,
    sido=selected_sido,
    sgg_list=selected_sgg,
    pyeong_group=selected_pyeong,
    min_amount=min_amount,
    max_amount=max_amount
)
render_kpi_cards(kpis)

st.markdown("<br>", unsafe_allow_html=True)

# 2. 인터랙티브 비주얼 차트 영역
col_left, col_right = st.columns([6, 4])

with col_left:
    df_trend = get_daily_trend(parquet_path, sido=selected_sido, sgg_list=selected_sgg, pyeong_group=selected_pyeong)
    fig_trend = create_trend_chart(df_trend)
    st.plotly_chart(fig_trend, use_container_width=True)

with col_right:
    df_regions = get_top_regions(parquet_path, sido=selected_sido, limit=10)
    fig_regions = create_region_bar_chart(df_regions)
    st.plotly_chart(fig_regions, use_container_width=True)

# 평형대별 분포 박스플롯
df_dist = get_price_distribution(parquet_path, sido=selected_sido, sgg_list=selected_sgg)
fig_box = create_price_box_plot(df_dist)
st.plotly_chart(fig_box, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# 3. 하단 탭 영역: 최고가 랭킹, 전체 실거래 테이블, 다운로드
tab1, tab2, tab3 = st.tabs(["👑 최고가 거래 TOP 20", "📋 실거래가 상세 테이블", "💾 데이터 다운로드"])

with tab1:
    st.markdown("#### 🏆 선택 지역 최근 7일 최고가 거래 아파트")
    df_top = get_top_deals(parquet_path, sido=selected_sido, limit=20)
    if not df_top.empty:
        df_top_display = df_top.copy()
        df_top_display["거래금액"] = df_top_display["deal_amount"].apply(format_krw_amount)
        df_top_display["평당가격"] = df_top_display["price_per_pyeong"].apply(lambda x: f"{x:,.0f}만원")
        df_top_display = df_top_display.rename(columns={
            "deal_date": "계약일", "sido_name": "시도", "sgg_name": "시군구", "umd_nm": "법정동",
            "apt_name": "단지명", "exclusive_area": "전용(㎡)", "pyeong": "평형", "floor": "층",
            "build_year": "건축년도"
        })
        cols_order = ["계약일", "시도", "시군구", "법정동", "단지명", "거래금액", "평당가격", "평형", "전용(㎡)", "층", "건축년도"]
        st.dataframe(df_top_display[cols_order], use_container_width=True, hide_index=True)
    else:
        st.info("해당 조건의 거래 내역이 없습니다.")

with tab2:
    st.markdown("#### 🔎 필터링된 전체 실거래 상세 데이터")
    df_filtered = get_filtered_deals(
        parquet_path,
        sido=selected_sido,
        sgg_list=selected_sgg,
        pyeong_group=selected_pyeong,
        min_amount=min_amount,
        max_amount=max_amount
    )
    if not df_filtered.empty:
        st.caption(f"총 {len(df_filtered):,} 건의 거래가 검색되었습니다.")
        st.dataframe(df_filtered, use_container_width=True, hide_index=True)
    else:
        st.info("검색 조건에 맞는 거래 데이터가 없습니다.")

with tab3:
    st.markdown("#### 📥 실거래 데이터 CSV 다운로드")
    if not df_filtered.empty:
        csv_data = df_filtered.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📄 필터링된 데이터 CSV 파일 다운로드",
            data=csv_data,
            file_name=f"apt_deals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.warning("다운로드할 데이터가 없습니다.")

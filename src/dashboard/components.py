import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

def format_krw_amount(amount_manwon: int | float) -> str:
    """만원 단위 숫자를 한글 억/만원 단위 문자열로 변환 (예: 12500 -> '1억 2,500만원')"""
    if amount_manwon is None or amount_manwon <= 0:
        return "0원"
    amount = int(round(amount_manwon))
    eok = amount // 10000
    rem = amount % 10000

    if eok > 0 and rem > 0:
        return f"{eok}억 {rem:,}만원"
    elif eok > 0 and rem == 0:
        return f"{eok}억원"
    else:
        return f"{rem:,}만원"

def create_trend_chart(df_trend: pd.DataFrame) -> go.Figure:
    """일자별 거래량(Bar) 및 평균 거래금액(Line) 복합 차트"""
    if df_trend.empty:
        fig = go.Figure()
        fig.update_layout(title="데이터가 없습니다.")
        return fig

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 거래건수 (Bar)
    fig.add_trace(
        go.Bar(
            x=df_trend["deal_date"],
            y=df_trend["deal_count"],
            name="거래건수 (건)",
            marker_color="#3B82F6",
            opacity=0.85,
            hovertemplate="<b>%{x}</b><br>거래건수: %{y:,}건<extra></extra>"
        ),
        secondary_y=False
    )

    # 평균 거래금액 (Line)
    fig.add_trace(
        go.Scatter(
            x=df_trend["deal_date"],
            y=df_trend["avg_amount"],
            name="평균 거래가 (만원)",
            mode="lines+markers",
            line=dict(color="#EF4444", width=3),
            marker=dict(size=7, color="#EF4444"),
            hovertemplate="<b>%{x}</b><br>평균 거래가: %{y:,.0f}만원<extra></extra>"
        ),
        secondary_y=True
    )

    fig.update_layout(
        title="<b>📅 일자별 실거래 건수 및 평균 매매가 추이</b>",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(title_text="계약일자", showgrid=True, gridcolor="#E5E7EB")
    fig.update_yaxes(title_text="거래건수 (건)", secondary_y=False, showgrid=True, gridcolor="#E5E7EB")
    fig.update_yaxes(title_text="평균 거래금액 (만원)", secondary_y=True, showgrid=False)

    return fig

def create_region_bar_chart(df_regions: pd.DataFrame) -> go.Figure:
    """지역별 거래량 TOP N 수평 막대 차트"""
    if df_regions.empty:
        fig = go.Figure()
        fig.update_layout(title="데이터가 없습니다.")
        return fig

    # 보기 좋게 오름차순 정렬 (수평 바 상단에 1위가 오도록)
    df_sorted = df_regions.sort_values(by="deal_count", ascending=True)

    fig = go.Figure(
        go.Bar(
            x=df_sorted["deal_count"],
            y=df_sorted["region"],
            orientation="h",
            marker=dict(
                color=df_sorted["deal_count"],
                colorscale="Viridis",
                showscale=False
            ),
            text=[f"{c:,}건 ({format_krw_amount(a)})" for c, a in zip(df_sorted["deal_count"], df_sorted["avg_amount"])],
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>거래량: %{x:,}건<extra></extra>"
        )
    )

    fig.update_layout(
        title="<b>🏆 지역별 거래량 TOP 10 및 평균가</b>",
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="거래건수 (건)", showgrid=True, gridcolor="#E5E7EB"),
        yaxis=dict(title="지역"),
    )

    return fig

def create_price_box_plot(df_dist: pd.DataFrame) -> go.Figure:
    """평형대별 거래 금액 분포 박스플롯"""
    if df_dist.empty:
        fig = go.Figure()
        fig.update_layout(title="데이터가 없습니다.")
        return fig

    category_order = ["소형 (<59㎡)", "중소형 (59~84㎡)", "국민평형 (84~102㎡)", "대형 (102㎡+)"]
    available_hover = [c for c in ["apt_name", "deal_date"] if c in df_dist.columns]
    
    fig = px.box(
        df_dist,
        x="pyeong_category",
        y="deal_amount",
        color="pyeong_category",
        category_orders={"pyeong_category": category_order},
        points="outliers",
        hover_data=available_hover if available_hover else None
    )

    fig.update_layout(
        title="<b>📊 평형대별 거래가격 분포 (만원)</b>",
        showlegend=False,
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title="평형 구분", showgrid=True, gridcolor="#E5E7EB"),
        yaxis=dict(title="거래금액 (만원)", showgrid=True, gridcolor="#E5E7EB"),
    )

    return fig

def render_kpi_cards(kpi_data: dict) -> None:
    """상단 주요 통계 KPI 메트릭 카드 4종 렌더링"""
    col1, col2, col3, col4 = st.columns(4)

    total_count = kpi_data.get("total_count", 0)
    avg_amount = kpi_data.get("avg_amount", 0)
    avg_pyeong_price = kpi_data.get("avg_pyeong_price", 0.0)
    max_amount = kpi_data.get("max_amount", 0)
    max_apt = kpi_data.get("max_apt_name", "-")

    with col1:
        st.metric(
            label="📈 최근 7일 총 거래건수",
            value=f"{total_count:,} 건"
        )
    with col2:
        st.metric(
            label="💰 평균 실거래가",
            value=format_krw_amount(avg_amount),
            help="필터링된 거래 건들의 평균 매매가격"
        )
    with col3:
        st.metric(
            label="📐 평당(3.3㎡) 평균가격",
            value=format_krw_amount(avg_pyeong_price),
            help="전용면적 기준 3.3㎡당 환산 평균 단가"
        )
    with col4:
        st.metric(
            label="👑 최고가 거래 단지",
            value=format_krw_amount(max_amount),
            delta=f"단지: {max_apt}" if max_apt != "-" else None,
            delta_color="normal"
        )

import pandas as pd
from src.dashboard.components import (
    format_krw_amount, create_trend_chart, create_region_bar_chart, create_price_box_plot
)

def test_format_krw_amount():
    assert format_krw_amount(12500) == "1억 2,500만원"
    assert format_krw_amount(8500) == "8,500만원"
    assert format_krw_amount(300000) == "30억원"
    assert format_krw_amount(0) == "0원"
    assert format_krw_amount(450) == "450만원"

def test_create_trend_chart():
    df = pd.DataFrame([
        {"deal_date": "2026-09-27", "deal_count": 15, "avg_amount": 75000},
        {"deal_date": "2026-09-28", "deal_count": 25, "avg_amount": 82000}
    ])
    fig = create_trend_chart(df)
    assert fig is not None
    assert len(fig.data) == 2  # 거래량 바 + 평균가격 라인

def test_create_region_bar_chart():
    df = pd.DataFrame([
        {"region": "강남구", "deal_count": 50, "avg_amount": 250000},
        {"region": "서초구", "deal_count": 30, "avg_amount": 220000}
    ])
    fig = create_region_bar_chart(df)
    assert fig is not None
    assert len(fig.data) == 1

def test_create_price_box_plot():
    df = pd.DataFrame([
        {"pyeong_category": "국민평형 (84~102㎡)", "deal_amount": 95000, "apt_name": "힐스테이트"},
        {"pyeong_category": "소형 (<59㎡)", "deal_amount": 45000, "apt_name": "자이"}
    ])
    fig = create_price_box_plot(df)
    assert fig is not None

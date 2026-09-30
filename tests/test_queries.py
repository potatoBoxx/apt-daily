import duckdb
import pandas as pd
import pytest
from src.dashboard.queries import (
    get_kpis, get_daily_trend, get_top_regions, get_top_deals, get_filtered_deals
)

@pytest.fixture
def sample_parquet(tmp_path):
    parquet_path = str(tmp_path / "test_deals.parquet")
    sample_data = [
        {
            "deal_hash": "h1", "deal_date": "2026-09-28", "sgg_cd": "11680",
            "sido_name": "서울특별시", "sgg_name": "강남구", "umd_nm": "압구정동",
            "apt_name": "현대1차", "exclusive_area": 84.5, "pyeong": 25.6,
            "floor": 10, "deal_amount": 420000, "price_per_pyeong": 16406.2,
            "build_year": 1976, "cancel_deal_type": ""
        },
        {
            "deal_hash": "h2", "deal_date": "2026-09-28", "sgg_cd": "11680",
            "sido_name": "서울특별시", "sgg_name": "강남구", "umd_nm": "대치동",
            "apt_name": "은마", "exclusive_area": 76.79, "pyeong": 23.2,
            "floor": 8, "deal_amount": 260000, "price_per_pyeong": 11206.9,
            "build_year": 1979, "cancel_deal_type": ""
        },
        {
            "deal_hash": "h3", "deal_date": "2026-09-27", "sgg_cd": "41135",
            "sido_name": "경기도", "sgg_name": "성남시 분당구", "umd_nm": "정자동",
            "apt_name": "파크뷰", "exclusive_area": 84.99, "pyeong": 25.7,
            "floor": 15, "deal_amount": 185000, "price_per_pyeong": 7198.4,
            "build_year": 2004, "cancel_deal_type": ""
        }
    ]
    df = pd.DataFrame(sample_data)
    df.to_parquet(parquet_path, index=False)
    return parquet_path

def test_get_kpis_all(sample_parquet):
    kpis = get_kpis(sample_parquet, sido="전체")
    assert kpis["total_count"] == 3
    assert kpis["avg_amount"] == round((420000 + 260000 + 185000) / 3)
    assert kpis["max_amount"] == 420000
    assert kpis["max_apt_name"] == "현대1차"

def test_get_kpis_filtered_sido(sample_parquet):
    kpis = get_kpis(sample_parquet, sido="경기도")
    assert kpis["total_count"] == 1
    assert kpis["avg_amount"] == 185000
    assert kpis["max_apt_name"] == "파크뷰"

def test_get_daily_trend(sample_parquet):
    df_trend = get_daily_trend(sample_parquet, sido="전체")
    assert len(df_trend) == 2  # 2026-09-27, 2026-09-28
    assert "deal_date" in df_trend.columns
    assert "deal_count" in df_trend.columns
    assert "avg_amount" in df_trend.columns

def test_get_top_regions(sample_parquet):
    df_top = get_top_regions(sample_parquet, sido="전체", limit=10)
    assert len(df_top) >= 1
    assert "region" in df_top.columns
    assert "deal_count" in df_top.columns

def test_get_top_deals(sample_parquet):
    df_top_deals = get_top_deals(sample_parquet, sido="전체", limit=2)
    assert len(df_top_deals) == 2
    assert df_top_deals.iloc[0]["apt_name"] == "현대1차"
    assert df_top_deals.iloc[0]["deal_amount"] == 420000

def test_daily_query_functions(sample_parquet):
    from src.dashboard.queries import get_available_dates, get_daily_market_metrics, get_daily_deals_table
    dates = get_available_dates(sample_parquet)
    assert dates == ["2026-09-28", "2026-09-27"]

    metrics = get_daily_market_metrics(sample_parquet, "2026-09-28")
    assert metrics["deal_count"] == 2
    assert metrics["avg_amount"] == 340000
    assert metrics["max_amount"] == 420000
    assert "top3_deals" in metrics
    assert len(metrics["top3_deals"]) == 2
    assert metrics["top3_deals"][0]["apt_name"] == "현대1차"

    table = get_daily_deals_table(sample_parquet, "2026-09-28")
    assert len(table) == 2
    assert (table["deal_date"] == "2026-09-28").all()


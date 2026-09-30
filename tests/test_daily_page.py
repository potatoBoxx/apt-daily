import pytest
from unittest.mock import patch
import pandas as pd

def test_daily_page_dependencies_and_logic(tmp_path):
    # 페이지에서 호출하는 핵심 함수들이 에러 없이 동작하는지 단위 검증
    from src.dashboard.queries import get_available_dates, get_daily_deals_table, get_daily_market_metrics
    from src.analyzer import get_or_create_daily_analysis

    parquet_file = str(tmp_path / "smoke.parquet")
    db_file = str(tmp_path / "smoke.db")

    sample_data = [{
        "deal_hash": "d1", "deal_date": "2026-09-28", "sgg_cd": "11110",
        "sido_name": "서울특별시", "sgg_name": "종로구", "umd_nm": "평창동",
        "apt_name": "평창롯데", "exclusive_area": 84.9, "pyeong": 25.7,
        "floor": 3, "deal_amount": 95000, "price_per_pyeong": 3696.5,
        "build_year": 2000, "cancel_deal_type": ""
    }]
    pd.DataFrame(sample_data).to_parquet(parquet_file, index=False)

    dates = get_available_dates(parquet_file)
    assert dates == ["2026-09-28"]

    metrics = get_daily_market_metrics(parquet_file, "2026-09-28")
    assert metrics["deal_count"] == 1

    table = get_daily_deals_table(parquet_file, "2026-09-28")
    assert len(table) == 1

    with patch("src.analyzer.call_gemini_api", return_value="### Mock Report"):
        summary, is_cached = get_or_create_daily_analysis(
            deal_date="2026-09-28",
            parquet_path=parquet_file,
            db_path=db_file,
            api_key="test_key"
        )
        assert summary["summary_markdown"] == "### Mock Report"
        assert is_cached is False

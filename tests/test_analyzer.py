from unittest.mock import patch
import pytest
import pandas as pd

from src.storage import init_db, save_daily_summary, get_daily_summary

@pytest.fixture
def test_env(tmp_path):
    db_file = str(tmp_path / "test_analyzer.db")
    parquet_file = str(tmp_path / "test_analyzer.parquet")
    init_db(db_file)

    sample_deals = [
        {
            "deal_hash": "a1", "deal_date": "2026-09-28", "sgg_cd": "11680",
            "sido_name": "서울특별시", "sgg_name": "강남구", "umd_nm": "압구정동",
            "apt_name": "신현대", "exclusive_area": 84.5, "pyeong": 25.6,
            "floor": 10, "deal_amount": 450000, "price_per_pyeong": 17578.1,
            "build_year": 1982, "cancel_deal_type": ""
        }
    ]
    pd.DataFrame(sample_deals).to_parquet(parquet_file, index=False)
    return {"db": db_file, "parquet": parquet_file}

def test_build_analyst_prompt():
    from src.analyzer import build_analyst_prompt
    metrics = {
        "deal_date": "2026-09-28",
        "deal_count": 50,
        "avg_amount": 42000,
        "avg_pyeong_price": 1450.0,
        "max_amount": 450000,
        "capital_ratio": 62.5,
        "top3_deals": [
            {"apt_name": "신현대", "sido_name": "서울특별시", "sgg_name": "강남구", "deal_amount": 450000, "pyeong": 25.6, "floor": 10}
        ],
        "size_dist": {"국민평형 (84~102㎡)": 30}
    }
    prompt = build_analyst_prompt("2026-09-28", metrics)
    assert "2026-09-28" in prompt
    assert "신현대" in prompt
    assert "부동산 전문" in prompt
    assert "마켓 브리핑" in prompt

def test_cache_hit_does_not_call_gemini_api(test_env):
    from src.analyzer import get_or_create_daily_analysis

    # 1. 미리 DB에 요약 저장
    save_daily_summary(
        "2026-09-28",
        "### 기존 캐시된 분석 내용",
        {"deal_count": 1, "avg_amount": 450000, "max_amount": 450000},
        model_name="gemini-1.5-flash",
        db_path=test_env["db"]
    )

    # 2. get_or_create_daily_analysis 호출 시 call_gemini_api가 호출되지 않아야 함
    with patch("src.analyzer.call_gemini_api") as mock_gemini:
        res, is_cached = get_or_create_daily_analysis(
            deal_date="2026-09-28",
            parquet_path=test_env["parquet"],
            db_path=test_env["db"],
            api_key="test_dummy_key"
        )
        assert mock_gemini.call_count == 0
        assert is_cached is True
        assert res["summary_markdown"] == "### 기존 캐시된 분석 내용"

def test_cache_miss_calls_gemini_and_saves_to_db(test_env):
    from src.analyzer import get_or_create_daily_analysis

    # 1. DB에 요약이 없는 상태에서 호출
    with patch("src.analyzer.call_gemini_api", return_value="### Gemini 신규 생성 분석") as mock_gemini:
        res, is_cached = get_or_create_daily_analysis(
            deal_date="2026-09-28",
            parquet_path=test_env["parquet"],
            db_path=test_env["db"],
            api_key="test_dummy_key"
        )
        assert mock_gemini.call_count == 1
        assert is_cached is False
        assert res["summary_markdown"] == "### Gemini 신규 생성 분석"

    # 2. 실제로 DB에 저장되었는지 확인
    saved = get_daily_summary("2026-09-28", db_path=test_env["db"])
    assert saved is not None
    assert saved["summary_markdown"] == "### Gemini 신규 생성 분석"

def test_force_refresh_updates_db(test_env):
    from src.analyzer import get_or_create_daily_analysis

    # 1. 기존 데이터 저장
    save_daily_summary(
        "2026-09-28",
        "### 구버전 요약",
        {"deal_count": 1, "avg_amount": 450000, "max_amount": 450000},
        db_path=test_env["db"]
    )

    # 2. force_refresh=True로 호출하면 재호출되어야 함
    with patch("src.analyzer.call_gemini_api", return_value="### 새로고침된 신규 요약") as mock_gemini:
        res, is_cached = get_or_create_daily_analysis(
            deal_date="2026-09-28",
            parquet_path=test_env["parquet"],
            db_path=test_env["db"],
            api_key="test_dummy_key",
            force_refresh=True
        )
        assert mock_gemini.call_count == 1
        assert is_cached is False
        assert res["summary_markdown"] == "### 새로고침된 신규 요약"

def test_error_cache_is_auto_invalidated_and_regenerated(test_env):
    from src.analyzer import get_or_create_daily_analysis

    # 1. DB에 이전 오류 메시지가 저장되어 있는 상태
    save_daily_summary(
        "2026-09-28",
        "⚠️ Gemini AI 분석 생성 중 오류가 발생했습니다: 404 Not Found",
        {"deal_count": 1, "avg_amount": 450000, "max_amount": 450000},
        model_name="gemini-1.5-flash",
        db_path=test_env["db"]
    )

    # 2. 조회 시 오류 캐시를 무시하고 자동으로 재분석(API 호출)을 수행해야 함
    with patch("src.analyzer.call_gemini_api", return_value="### 정상 복구된 신규 분석 리포트") as mock_gemini:
        res, is_cached = get_or_create_daily_analysis(
            deal_date="2026-09-28",
            parquet_path=test_env["parquet"],
            db_path=test_env["db"],
            api_key="test_dummy_key"
        )
        assert mock_gemini.call_count == 1
        assert is_cached is False
        assert res["summary_markdown"] == "### 정상 복구된 신규 분석 리포트"

    # 3. DB에도 정상 분석 결과로 갱신되었는지 확인
    saved = get_daily_summary("2026-09-28", db_path=test_env["db"])
    assert saved is not None
    assert saved["summary_markdown"] == "### 정상 복구된 신규 분석 리포트"

def test_failed_call_is_not_saved_to_db(test_env):
    from src.analyzer import get_or_create_daily_analysis

    # 1. API 호출이 오류 메시지를 반환할 때
    with patch("src.analyzer.call_gemini_api", return_value="⚠️ Gemini AI 분석 생성 중 오류가 발생했습니다: 503") as mock_gemini:
        res, is_cached = get_or_create_daily_analysis(
            deal_date="2026-09-28",
            parquet_path=test_env["parquet"],
            db_path=test_env["db"],
            api_key="test_dummy_key"
        )
        assert mock_gemini.call_count == 1
        assert res["summary_markdown"].startswith("⚠️")

    # 2. 오류 메시지는 DB에 영구 저장되지 않아야 함
    saved = get_daily_summary("2026-09-28", db_path=test_env["db"])
    assert saved is None


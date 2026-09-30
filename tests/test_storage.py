from pathlib import Path
import duckdb
from src.storage import init_db, save_to_sqlite, export_to_parquet

def test_sqlite_upsert_and_parquet_export(tmp_path):
    db_file = str(tmp_path / "test.db")
    parquet_file = str(tmp_path / "test.parquet")
    init_db(db_file)
    
    mock_items = [{
        "deal_hash": "hash_sample_1",
        "deal_date": "2026-09-28",
        "sgg_cd": "11110",
        "sido_name": "서울특별시",
        "sgg_name": "종로구",
        "umd_nm": "청운동",
        "apt_name": "인왕산아이파크",
        "exclusive_area": 84.85,
        "pyeong": 25.7,
        "floor": 5,
        "deal_amount": 105000,
        "price_per_pyeong": 4085.6,
        "build_year": 2008,
        "cancel_deal_type": ""
    }]
    
    # 1. 첫 번째 저장: 1건 삽입되어야 함
    inserted = save_to_sqlite(mock_items, db_file)
    assert inserted == 1
    
    # 2. 동일한 데이터 재저장: 중복(deal_hash 충돌)으로 무시되어 0건이어야 함
    inserted_again = save_to_sqlite(mock_items, db_file)
    assert inserted_again == 0
    
    # 3. Parquet 내보내기 검증
    exported = export_to_parquet(db_file, parquet_file, days=7)
    assert exported == 1
    assert Path(parquet_file).exists()
    
    # 4. DuckDB로 생성된 Parquet 파일 읽기 및 데이터 정합성 검증
    res = duckdb.query(f"SELECT apt_name, deal_amount, sido_name FROM read_parquet('{parquet_file}')").fetchall()
    assert len(res) == 1
    assert res[0][0] == "인왕산아이파크"
    assert res[0][1] == 105000
    assert res[0][2] == "서울특별시"

def test_ai_daily_summary_crud(tmp_path):
    from src.storage import init_db, get_daily_summary, save_daily_summary
    db_file = str(tmp_path / "test_summary.db")
    init_db(db_file)

    # 1. 초기 조회: None
    assert get_daily_summary("2026-09-28", db_path=db_file) is None

    # 2. 저장
    stats = {"deal_count": 100, "avg_amount": 45000, "max_amount": 150000}
    saved = save_daily_summary("2026-09-28", "### 분석 요약", stats, model_name="gemini-1.5-flash", db_path=db_file)
    assert saved is True

    # 3. 재조회: 저장된 데이터 반환
    summary = get_daily_summary("2026-09-28", db_path=db_file)
    assert summary is not None
    assert summary["deal_date"] == "2026-09-28"
    assert summary["summary_markdown"] == "### 분석 요약"
    assert summary["deal_count"] == 100
    assert summary["avg_amount"] == 45000
    assert summary["max_amount"] == 150000
    assert summary["model_name"] == "gemini-1.5-flash"
    assert summary["refresh_count"] == 0

def test_refresh_count_and_json_sync(tmp_path):
    import json
    from src.storage import init_db, get_daily_summary, save_daily_summary, export_ai_summaries_to_json, sync_ai_summaries_from_json

    db_file = str(tmp_path / "test_sync.db")
    json_file = str(tmp_path / "test_summaries.json")
    init_db(db_file)

    # 1. 초기 저장 (refresh_count = 0)
    stats = {"deal_count": 50, "avg_amount": 40000, "max_amount": 100000}
    save_daily_summary("2026-09-28", "### 첫 리포트", stats, db_path=db_file, refresh_count=0)
    
    row = get_daily_summary("2026-09-28", db_path=db_file)
    assert row["refresh_count"] == 0

    # 2. 1회 재분석 저장 (refresh_count = 1)
    save_daily_summary("2026-09-28", "### 재생성 리포트", stats, db_path=db_file, refresh_count=1)
    row_updated = get_daily_summary("2026-09-28", db_path=db_file)
    assert row_updated["refresh_count"] == 1
    assert row_updated["summary_markdown"] == "### 재생성 리포트"

    # 3. JSON으로 내보내기 검증
    export_count = export_ai_summaries_to_json(db_file, json_file)
    assert export_count == 1
    assert Path(json_file).exists()

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "2026-09-28" in data
    assert data["2026-09-28"]["refresh_count"] == 1

    # 4. 빈 DB에 JSON으로부터 복원 검증
    new_db_file = str(tmp_path / "restored.db")
    init_db(new_db_file)
    synced_count = sync_ai_summaries_from_json(json_file, new_db_file)
    assert synced_count == 1

    restored_row = get_daily_summary("2026-09-28", db_path=new_db_file)
    assert restored_row is not None
    assert restored_row["summary_markdown"] == "### 재생성 리포트"
    assert restored_row["refresh_count"] == 1


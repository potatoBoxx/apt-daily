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

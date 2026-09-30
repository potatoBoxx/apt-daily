import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

DEFAULT_DB_PATH = "data/apt_deals.db"
DEFAULT_PARQUET_PATH = "data/latest_deals.parquet"

DDL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS apt_trades (
    deal_hash TEXT PRIMARY KEY,
    deal_date TEXT NOT NULL,
    sgg_cd TEXT NOT NULL,
    sido_name TEXT NOT NULL,
    sgg_name TEXT NOT NULL,
    umd_nm TEXT NOT NULL,
    apt_name TEXT NOT NULL,
    exclusive_area REAL NOT NULL,
    pyeong REAL NOT NULL,
    floor INTEGER,
    deal_amount INTEGER NOT NULL,
    price_per_pyeong REAL NOT NULL,
    build_year INTEGER,
    cancel_deal_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trades_date ON apt_trades(deal_date);
CREATE INDEX IF NOT EXISTS idx_trades_sido ON apt_trades(sido_name, sgg_name);
"""

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """SQLite 데이터베이스 및 테이블 초기화"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL_CREATE_TABLE)
        conn.commit()

def save_to_sqlite(items: list[dict], db_path: str = DEFAULT_DB_PATH) -> int:
    """
    정제된 실거래가 데이터 리스트를 SQLite에 저장합니다.
    deal_hash를 기준으로 이미 존재하는 거래는 무시(INSERT OR IGNORE)합니다.
    새롭게 저장된 거래 건수를 반환합니다.
    """
    if not items:
        return 0

    init_db(db_path)
    insert_sql = """
    INSERT OR IGNORE INTO apt_trades (
        deal_hash, deal_date, sgg_cd, sido_name, sgg_name, umd_nm,
        apt_name, exclusive_area, pyeong, floor, deal_amount,
        price_per_pyeong, build_year, cancel_deal_type
    ) VALUES (
        :deal_hash, :deal_date, :sgg_cd, :sido_name, :sgg_name, :umd_nm,
        :apt_name, :exclusive_area, :pyeong, :floor, :deal_amount,
        :price_per_pyeong, :build_year, :cancel_deal_type
    )
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        total_rows_before = conn.total_changes
        cursor.executemany(insert_sql, items)
        conn.commit()
        inserted_count = conn.total_changes - total_rows_before
        return inserted_count

def export_to_parquet(db_path: str = DEFAULT_DB_PATH,
                      parquet_path: str = DEFAULT_PARQUET_PATH,
                      days: int = 7) -> int:
    """
    SQLite DB에서 최근 days 일간의 계약 데이터를 조회하여
    고압축 Parquet 파일로 저장합니다. 내보낸 레코드 수를 반환합니다.
    """
    if not Path(db_path).exists():
        return 0

    out_file = Path(parquet_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        if days > 0:
            target_date = (datetime.now().date() - timedelta(days=days)).strftime("%Y-%m-%d")
            query = f"SELECT * FROM apt_trades WHERE deal_date >= '{target_date}' ORDER BY deal_date DESC"
        else:
            query = "SELECT * FROM apt_trades ORDER BY deal_date DESC"

        df = pd.read_sql_query(query, conn)

    if df.empty:
        # 빈 데이터프레임일 때도 컬럼 스키마를 유지한 Parquet 파일 생성
        df.to_parquet(parquet_path, index=False, compression="snappy")
        return 0

    df.to_parquet(parquet_path, index=False, compression="snappy")
    return len(df)

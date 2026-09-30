import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

DEFAULT_DB_PATH = "data/apt_deals.db"
DEFAULT_PARQUET_PATH = "data/latest_deals.parquet"
DEFAULT_AI_SUMMARIES_JSON_PATH = "data/ai_daily_summaries.json"

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
CREATE TABLE IF NOT EXISTS ai_daily_summaries (
    deal_date TEXT PRIMARY KEY,
    summary_markdown TEXT NOT NULL,
    deal_count INTEGER NOT NULL,
    avg_amount INTEGER NOT NULL,
    max_amount INTEGER NOT NULL,
    model_name TEXT DEFAULT 'gemini-1.5-flash',
    refresh_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """SQLite 데이터베이스 및 테이블 초기화 및 스키마 마이그레이션"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL_CREATE_TABLE)
        try:
            conn.execute("ALTER TABLE ai_daily_summaries ADD COLUMN refresh_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
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

def get_daily_summary(deal_date: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    """SQLite DB에서 특정 일자의 AI 분석 요약 레코드를 조회하여 반환합니다."""
    if not Path(db_path).exists():
        return None
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT deal_date, summary_markdown, deal_count, avg_amount, max_amount, model_name, refresh_count, created_at
            FROM ai_daily_summaries
            WHERE deal_date = ?
            """,
            (deal_date,)
        )
        row = cursor.fetchone()
        if row:
            data = dict(row)
            if "refresh_count" not in data or data["refresh_count"] is None:
                data["refresh_count"] = 0
            return data
        return None

def save_daily_summary(deal_date: str, summary_markdown: str, stats: dict,
                       model_name: str = "gemini-1.5-flash",
                       db_path: str = DEFAULT_DB_PATH,
                       refresh_count: int | None = None) -> bool:
    """Gemini가 생성한 특정 일자의 분석 요약을 SQLite DB에 영구 저장(UPSERT)합니다."""
    init_db(db_path)
    if refresh_count is None:
        existing = get_daily_summary(deal_date, db_path)
        refresh_count = existing["refresh_count"] if existing and "refresh_count" in existing else 0

    sql = """
    INSERT OR REPLACE INTO ai_daily_summaries (
        deal_date, summary_markdown, deal_count, avg_amount, max_amount, model_name, refresh_count, created_at
    ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
    )
    """
    deal_count = stats.get("deal_count", 0)
    avg_amount = stats.get("avg_amount", 0)
    max_amount = stats.get("max_amount", 0)
    with sqlite3.connect(db_path) as conn:
        conn.execute(sql, (deal_date, summary_markdown, deal_count, avg_amount, max_amount, model_name, refresh_count))
        conn.commit()
    return True

def export_ai_summaries_to_json(db_path: str = DEFAULT_DB_PATH,
                                json_path: str = DEFAULT_AI_SUMMARIES_JSON_PATH) -> int:
    """SQLite의 모든 AI 일일 요약 데이터를 JSON 파일로 내보냅니다."""
    if not Path(db_path).exists():
        return 0
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT deal_date, summary_markdown, deal_count, avg_amount, max_amount, model_name, refresh_count, created_at
            FROM ai_daily_summaries
            ORDER BY deal_date DESC
            """
        )
        rows = cursor.fetchall()

    data = {}
    for row in rows:
        d = dict(row)
        if "created_at" in d and isinstance(d["created_at"], datetime):
            d["created_at"] = d["created_at"].isoformat()
        deal_date = d["deal_date"]
        data[deal_date] = d

    out_file = Path(json_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return len(data)

def sync_ai_summaries_from_json(json_path: str = DEFAULT_AI_SUMMARIES_JSON_PATH,
                                db_path: str = DEFAULT_DB_PATH) -> int:
    """JSON 파일의 요약 데이터를 SQLite DB로 복원/동기화합니다."""
    path = Path(json_path)
    if not path.exists():
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    synced = 0
    for deal_date, item in data.items():
        existing = get_daily_summary(deal_date, db_path)
        if not existing:
            stats = {
                "deal_count": item.get("deal_count", 0),
                "avg_amount": item.get("avg_amount", 0),
                "max_amount": item.get("max_amount", 0),
            }
            save_daily_summary(
                deal_date=deal_date,
                summary_markdown=item.get("summary_markdown", ""),
                stats=stats,
                model_name=item.get("model_name", "gemini-1.5-flash"),
                db_path=db_path,
                refresh_count=item.get("refresh_count", 0)
            )
            synced += 1

    return synced


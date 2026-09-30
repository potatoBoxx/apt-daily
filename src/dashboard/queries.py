from pathlib import Path
import duckdb
import pandas as pd

def _build_where(sido: str = "전체", sgg_list: list[str] | None = None,
                 pyeong_group: str = "전체", min_amount: int = 0,
                 max_amount: int = 0) -> tuple[str, list]:
    conditions = []
    params = []

    if sido and sido != "전체":
        conditions.append("sido_name = ?")
        params.append(sido)

    if sgg_list and len(sgg_list) > 0 and "전체" not in sgg_list:
        placeholders = ", ".join(["?"] * len(sgg_list))
        conditions.append(f"sgg_name IN ({placeholders})")
        params.extend(sgg_list)

    if pyeong_group and pyeong_group != "전체":
        if pyeong_group == "소형 (59㎡ 미만)":
            conditions.append("exclusive_area < 59.0")
        elif pyeong_group == "중소형 (59~84㎡ 미만)":
            conditions.append("exclusive_area >= 59.0 AND exclusive_area < 84.0")
        elif pyeong_group == "국민평형 (84~102㎡ 미만)":
            conditions.append("exclusive_area >= 84.0 AND exclusive_area < 102.0")
        elif pyeong_group == "대형 (102㎡ 이상)":
            conditions.append("exclusive_area >= 102.0")

    if min_amount > 0:
        conditions.append("deal_amount >= ?")
        params.append(min_amount)

    if max_amount > 0:
        conditions.append("deal_amount <= ?")
        params.append(max_amount)

    if conditions:
        return "WHERE " + " AND ".join(conditions), params
    return "", []

def get_kpis(parquet_path: str, sido: str = "전체", sgg_list: list[str] | None = None,
             pyeong_group: str = "전체", min_amount: int = 0, max_amount: int = 0) -> dict:
    """DuckDB 인메모리 엔진을 활용한 주요 KPI 집계"""
    if not Path(parquet_path).exists():
        return {"total_count": 0, "avg_amount": 0, "avg_pyeong_price": 0.0, "max_amount": 0, "max_apt_name": "-"}

    where_sql, params = _build_where(sido, sgg_list, pyeong_group, min_amount, max_amount)
    con = duckdb.connect()

    query = f"""
    SELECT
        COUNT(*) AS total_count,
        ROUND(COALESCE(AVG(deal_amount), 0), 0) AS avg_amount,
        ROUND(COALESCE(AVG(price_per_pyeong), 0), 1) AS avg_pyeong_price,
        COALESCE(MAX(deal_amount), 0) AS max_amount
    FROM read_parquet(?)
    {where_sql}
    """
    row = con.execute(query, [parquet_path] + params).fetchone()
    total_count, avg_amount, avg_pyeong_price, max_amount = row

    max_apt_name = "-"
    if max_amount > 0:
        query_max_apt = f"""
        SELECT apt_name
        FROM read_parquet(?)
        {where_sql} {'AND' if where_sql else 'WHERE'} deal_amount = ?
        LIMIT 1
        """
        apt_row = con.execute(query_max_apt, [parquet_path] + params + [max_amount]).fetchone()
        if apt_row:
            max_apt_name = apt_row[0]

    return {
        "total_count": int(total_count),
        "avg_amount": int(avg_amount),
        "avg_pyeong_price": float(avg_pyeong_price),
        "max_amount": int(max_amount),
        "max_apt_name": max_apt_name
    }

def get_daily_trend(parquet_path: str, sido: str = "전체", sgg_list: list[str] | None = None,
                    pyeong_group: str = "전체") -> pd.DataFrame:
    """일자별 거래량 및 평균 거래금액 추이 집계"""
    if not Path(parquet_path).exists():
        return pd.DataFrame(columns=["deal_date", "deal_count", "avg_amount"])

    where_sql, params = _build_where(sido, sgg_list, pyeong_group)
    con = duckdb.connect()

    query = f"""
    SELECT
        deal_date,
        COUNT(*) AS deal_count,
        ROUND(AVG(deal_amount), 0) AS avg_amount
    FROM read_parquet(?)
    {where_sql}
    GROUP BY deal_date
    ORDER BY deal_date ASC
    """
    return con.execute(query, [parquet_path] + params).df()

def get_top_regions(parquet_path: str, sido: str = "전체", limit: int = 10) -> pd.DataFrame:
    """지역별(시도/시군구) 거래량 TOP N 집계"""
    if not Path(parquet_path).exists():
        return pd.DataFrame(columns=["region", "deal_count", "avg_amount"])

    con = duckdb.connect()
    where_sql, params = _build_where(sido=sido)

    region_col = "sgg_name" if sido and sido != "전체" else "sido_name"
    query = f"""
    SELECT
        {region_col} AS region,
        COUNT(*) AS deal_count,
        ROUND(AVG(deal_amount), 0) AS avg_amount
    FROM read_parquet(?)
    {where_sql}
    GROUP BY {region_col}
    ORDER BY deal_count DESC
    LIMIT ?
    """
    return con.execute(query, [parquet_path] + params + [limit]).df()

def get_price_distribution(parquet_path: str, sido: str = "전체", sgg_list: list[str] | None = None) -> pd.DataFrame:
    """평형대별 거래 금액 분포 데이터 추출"""
    if not Path(parquet_path).exists():
        return pd.DataFrame(columns=["pyeong_category", "deal_amount", "apt_name"])

    where_sql, params = _build_where(sido, sgg_list)
    con = duckdb.connect()

    query = f"""
    SELECT
        CASE
            WHEN exclusive_area < 59.0 THEN '소형 (<59㎡)'
            WHEN exclusive_area < 84.0 THEN '중소형 (59~84㎡)'
            WHEN exclusive_area < 102.0 THEN '국민평형 (84~102㎡)'
            ELSE '대형 (102㎡+)'
        END AS pyeong_category,
        deal_amount,
        apt_name,
        deal_date
    FROM read_parquet(?)
    {where_sql}
    """
    return con.execute(query, [parquet_path] + params).df()

def get_top_deals(parquet_path: str, sido: str = "전체", limit: int = 20) -> pd.DataFrame:
    """최고가 거래 TOP N 목록"""
    if not Path(parquet_path).exists():
        return pd.DataFrame()

    where_sql, params = _build_where(sido=sido)
    con = duckdb.connect()

    query = f"""
    SELECT
        deal_date,
        sido_name,
        sgg_name,
        umd_nm,
        apt_name,
        exclusive_area,
        pyeong,
        floor,
        deal_amount,
        price_per_pyeong,
        build_year
    FROM read_parquet(?)
    {where_sql}
    ORDER BY deal_amount DESC
    LIMIT ?
    """
    return con.execute(query, [parquet_path] + params + [limit]).df()

def get_filtered_deals(parquet_path: str, sido: str = "전체", sgg_list: list[str] | None = None,
                       pyeong_group: str = "전체", min_amount: int = 0, max_amount: int = 0) -> pd.DataFrame:
    """필터링된 전체 실거래 상세 데이터 조회"""
    if not Path(parquet_path).exists():
        return pd.DataFrame()

    where_sql, params = _build_where(sido, sgg_list, pyeong_group, min_amount, max_amount)
    con = duckdb.connect()

    query = f"""
    SELECT
        deal_date AS "계약일자",
        sido_name AS "시도",
        sgg_name AS "시군구",
        umd_nm AS "법정동",
        apt_name AS "단지명",
        exclusive_area AS "전용면적(㎡)",
        pyeong AS "평형",
        floor AS "층",
        deal_amount AS "거래금액(만원)",
        price_per_pyeong AS "평당가격(만원)",
        build_year AS "건축년도"
    FROM read_parquet(?)
    {where_sql}
    ORDER BY deal_date DESC, deal_amount DESC
    """
    return con.execute(query, [parquet_path] + params).df()

def get_sgg_options(parquet_path: str, sido: str = "전체") -> list[str]:
    """선택된 시도에 해당하는 시군구 고유 목록 반환"""
    if not Path(parquet_path).exists():
        return []

    con = duckdb.connect()
    if sido and sido != "전체":
        query = "SELECT DISTINCT sgg_name FROM read_parquet(?) WHERE sido_name = ? ORDER BY sgg_name"
        rows = con.execute(query, [parquet_path, sido]).fetchall()
    else:
        query = "SELECT DISTINCT sgg_name FROM read_parquet(?) ORDER BY sgg_name"
        rows = con.execute(query, [parquet_path]).fetchall()

    return [r[0] for r in rows if r[0]]

def get_available_dates(parquet_path: str) -> list[str]:
    """Parquet 파일에 존재하는 모든 거래 일자(deal_date)를 내림차순으로 반환합니다."""
    if not Path(parquet_path).exists():
        return []

    con = duckdb.connect()
    query = "SELECT DISTINCT deal_date FROM read_parquet(?) ORDER BY deal_date DESC"
    rows = con.execute(query, [parquet_path]).fetchall()
    return [r[0] for r in rows if r[0]]

def get_daily_market_metrics(parquet_path: str, deal_date: str) -> dict:
    """특정 일자의 핵심 마켓 메트릭(Gemini AI 프롬프트 생성용)을 집계하여 반환합니다."""
    if not Path(parquet_path).exists():
        return {
            "deal_date": deal_date, "deal_count": 0, "avg_amount": 0,
            "avg_pyeong_price": 0.0, "max_amount": 0, "top3_deals": [],
            "capital_ratio": 0.0, "size_dist": {}
        }

    con = duckdb.connect()
    # 1. 일자 기초 통계
    query_stats = """
    SELECT
        COUNT(*) AS deal_count,
        COALESCE(ROUND(AVG(deal_amount), 0), 0) AS avg_amount,
        COALESCE(ROUND(AVG(price_per_pyeong), 1), 0.0) AS avg_pyeong_price,
        COALESCE(MAX(deal_amount), 0) AS max_amount,
        COALESCE(SUM(CASE WHEN sido_name IN ('서울특별시', '경기도', '인천광역시') THEN 1 ELSE 0 END), 0) AS capital_count
    FROM read_parquet(?)
    WHERE deal_date = ?
    """
    stats_row = con.execute(query_stats, [parquet_path, deal_date]).fetchone()
    deal_count = int(stats_row[0]) if stats_row else 0
    avg_amount = int(stats_row[1]) if stats_row else 0
    avg_pyeong_price = float(stats_row[2]) if stats_row else 0.0
    max_amount = int(stats_row[3]) if stats_row else 0
    capital_count = int(stats_row[4]) if stats_row else 0
    capital_ratio = round((capital_count / deal_count * 100), 1) if deal_count > 0 else 0.0

    # 2. 최고가 거래 TOP 3
    query_top3 = """
    SELECT
        apt_name, sido_name, sgg_name, umd_nm, pyeong, floor, deal_amount, price_per_pyeong
    FROM read_parquet(?)
    WHERE deal_date = ?
    ORDER BY deal_amount DESC
    LIMIT 3
    """
    top3_df = con.execute(query_top3, [parquet_path, deal_date]).df()
    top3_deals = top3_df.to_dict(orient="records")

    # 3. 평형대별 분포
    query_size = """
    SELECT
        CASE
            WHEN exclusive_area < 59.0 THEN '소형 (<59㎡)'
            WHEN exclusive_area < 84.0 THEN '중소형 (59~84㎡)'
            WHEN exclusive_area < 102.0 THEN '국민평형 (84~102㎡)'
            ELSE '대형 (102㎡+)'
        END AS size_group,
        COUNT(*) AS count
    FROM read_parquet(?)
    WHERE deal_date = ?
    GROUP BY size_group
    """
    size_df = con.execute(query_size, [parquet_path, deal_date]).df()
    size_dist = dict(zip(size_df["size_group"], size_df["count"])) if not size_df.empty else {}

    return {
        "deal_date": deal_date,
        "deal_count": deal_count,
        "avg_amount": avg_amount,
        "avg_pyeong_price": avg_pyeong_price,
        "max_amount": max_amount,
        "capital_count": capital_count,
        "capital_ratio": capital_ratio,
        "top3_deals": top3_deals,
        "size_dist": size_dist
    }

def get_daily_deals_table(parquet_path: str, deal_date: str, sido: str = "전체") -> pd.DataFrame:
    """특정 일자의 실거래 상세 테이블을 조회합니다."""
    if not Path(parquet_path).exists():
        return pd.DataFrame()

    con = duckdb.connect()
    conditions = ["deal_date = ?"]
    params = [deal_date]

    if sido and sido != "전체":
        conditions.append("sido_name = ?")
        params.append(sido)

    where_sql = "WHERE " + " AND ".join(conditions)
    query = f"""
    SELECT
        deal_date,
        sido_name,
        sgg_name,
        umd_nm,
        apt_name,
        exclusive_area,
        pyeong,
        floor,
        deal_amount,
        price_per_pyeong,
        build_year
    FROM read_parquet(?)
    {where_sql}
    ORDER BY deal_amount DESC
    """
    return con.execute(query, [parquet_path] + params).df()


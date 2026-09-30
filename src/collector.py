import argparse
import logging
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.parser import get_lawd_mapping, parse_trade_items, split_sido_sgg, generate_deal_hash
from src.storage import save_to_sqlite, export_to_parquet, DEFAULT_DB_PATH, DEFAULT_PARQUET_PATH

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("collector")

# 국토교통부 아파트 매매 실거래가 운영계정 엔드포인트
ENDPOINT_URL = os.getenv(
    "MOLIT_ENDPOINT_URL",
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
)

class AptTradeCollector:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("MOLIT_API_KEY", "").strip()
        self.lawd_map = get_lawd_mapping()

    def get_target_ym_list(self, days: int = 7) -> list[str]:
        """오늘 기준 최근 days 일에 걸치는 YYYYMM 목록 반환 (당월 및 월초일 경우 전월 포함)"""
        today = datetime.now().date()
        start_date = today - timedelta(days=days)
        
        yms = set()
        curr = start_date
        while curr <= today:
            yms.add(curr.strftime("%Y%m"))
            # 대략 다음 달 1일로 점프하거나 하루씩 증가
            curr += timedelta(days=1)
            
        return sorted(list(yms))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=False
    )
    def fetch_sgg(self, lawd_cd: str, deal_ymd: str) -> str | None:
        """단일 시군구 및 계약년월에 대한 API 요청"""
        if not self.api_key:
            return None

        params = {
            "serviceKey": self.api_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": "1",
            "numOfRows": "1000",
        }
        
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(ENDPOINT_URL, params=params)
            resp.raise_for_status()
            text = resp.text
            if "<resultCode>" in text and not ("<resultCode>00</resultCode>" in text or "<resultCode>000</resultCode>" in text):
                logger.warning(f"API 비정상 응답 ({lawd_cd}, {deal_ymd}): {text[:200]}")
            return text

    def generate_mock_data(self, count: int = 300, days: int = 7) -> list[dict]:
        """API 키가 없거나 테스트용인 경우 고품질 전국 가상 실거래 샘플 생성"""
        today = datetime.now().date()
        sgg_codes = list(self.lawd_map.keys())
        
        mock_apt_prefixes = ["래미안", "자이", "힐스테이트", "푸르지오", "아이파크", "더샵", "e편한세상", "롯데캐슬"]
        mock_apt_suffixes = ["센트럴", "파크", "포레스트", "퍼스트", "스카이", "그랑", "에비뉴", "베스트"]

        results = []
        for _ in range(count):
            day_offset = random.randint(0, days)
            deal_date = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            sgg_cd = random.choice(sgg_codes)
            full_loc = self.lawd_map.get(sgg_cd, "서울특별시 강남구")
            sido_name, sgg_name = split_sido_sgg(full_loc)
            umd_nm = f"{sgg_name.split()[-1]}동"
            
            apt_name = f"{random.choice(mock_apt_prefixes)}{random.choice(mock_apt_suffixes)}"
            area = random.choice([59.95, 74.80, 84.95, 101.5, 114.8, 134.2])
            floor = random.randint(1, 35)
            build_year = random.randint(1995, 2024)
            
            # 서울/경기 수도권은 가격대 높게 책정
            base_price = 100000 if sido_name in ["서울특별시", "경기도"] else 45000
            deal_amount = int(base_price * (area / 84.95) * random.uniform(0.7, 1.8))
            deal_amount = round(deal_amount, -2) # 백만원 단위 반올림

            pyeong = round(area / 3.30578, 1)
            price_per_pyeong = round(deal_amount / pyeong, 1)

            deal_hash = generate_deal_hash(
                deal_date=deal_date,
                sgg_cd=sgg_cd,
                umd_nm=umd_nm,
                apt_name=apt_name,
                exclusive_area=area,
                floor=floor,
                deal_amount=deal_amount
            )

            results.append({
                "deal_hash": deal_hash,
                "deal_date": deal_date,
                "sgg_cd": sgg_cd,
                "sido_name": sido_name,
                "sgg_name": sgg_name,
                "umd_nm": umd_nm,
                "apt_name": apt_name,
                "exclusive_area": area,
                "pyeong": pyeong,
                "floor": floor,
                "deal_amount": deal_amount,
                "price_per_pyeong": price_per_pyeong,
                "build_year": build_year,
                "cancel_deal_type": "",
            })
            
        return results

    def collect_all(self, days: int = 7, max_workers: int = 6,
                    db_path: str = DEFAULT_DB_PATH,
                    parquet_path: str = DEFAULT_PARQUET_PATH,
                    reset: bool = False) -> dict:
        """
        전국 250개 시군구의 최근 days일간 아파트 매매 실거래가를 수집하여
        SQLite에 저장하고 최신 Parquet 파일로 내보냅니다.
        """
        if reset:
            logger.info("기존 데이터베이스 및 Parquet 파일을 초기화(리셋)합니다.")
            if os.path.exists(db_path):
                os.remove(db_path)
            if os.path.exists(parquet_path):
                os.remove(parquet_path)

        today = datetime.now().date()
        target_start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        ym_list = self.get_target_ym_list(days=days)
        
        logger.info(f"수집 시작: 기준일 {today}, 대상 기간: {target_start_date} ~ {today}, 계약월: {ym_list}")
        
        if not self.api_key:
            logger.warning("MOLIT_API_KEY가 설정되지 않아 가상 Mock 샘플 데이터(500건)를 생성합니다.")
            items = self.generate_mock_data(count=500, days=days)
            inserted = save_to_sqlite(items, db_path)
            exported = export_to_parquet(db_path, parquet_path, days=days)
            return {"total_collected": len(items), "new_inserted": inserted, "exported": exported, "is_mock": True}

        all_parsed_items = []
        tasks = []
        for sgg_cd in self.lawd_map.keys():
            for ym in ym_list:
                tasks.append((sgg_cd, ym))

        logger.info(f"총 {len(tasks)}개 시군구 요청을 {max_workers}개 스레드로 수집합니다.")
        
        success_count = 0
        fail_count = 0
        completed_tasks = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(self.fetch_sgg, sgg_cd, ym): (sgg_cd, ym)
                for sgg_cd, ym in tasks
            }
            for future in as_completed(future_to_task):
                sgg_cd, ym = future_to_task[future]
                completed_tasks += 1
                try:
                    xml_text = future.result()
                    if xml_text:
                        parsed = parse_trade_items(xml_text, target_start_date=target_start_date, default_sgg_cd=sgg_cd)
                        all_parsed_items.extend(parsed)
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"오류 발생 ({sgg_cd}, {ym}): {e}")
                    fail_count += 1

                if completed_tasks % 50 == 0 or completed_tasks == len(tasks):
                    logger.info(f"진행 상황: {completed_tasks}/{len(tasks)} 완료 (누적 실거래 건수: {len(all_parsed_items)})")

        logger.info(f"수집 완료: 성공 {success_count}건, 실패 {fail_count}건, 총 추출 실거래 건수: {len(all_parsed_items)}")
        
        inserted = save_to_sqlite(all_parsed_items, db_path)
        exported = export_to_parquet(db_path, parquet_path, days=days)
        logger.info(f"SQLite 신규 삽입: {inserted}건, Parquet 내보내기: {exported}건")

        return {
            "total_collected": len(all_parsed_items),
            "new_inserted": inserted,
            "exported": exported,
            "is_mock": False
        }

def main():
    parser = argparse.ArgumentParser(description="전국 아파트 실거래가 수집기")
    parser.add_argument("--days", type=int, default=7, help="수집 기간 (일)")
    parser.add_argument("--mock", action="store_true", help="API 키 없이 목(Mock) 데이터로 수집 실행")
    parser.add_argument("--workers", type=int, default=6, help="동시 요청 워커 수")
    parser.add_argument("--reset", action="store_true", help="기존 DB 및 Parquet 파일을 삭제 후 초기화 수집")
    args = parser.parse_args()

    collector = AptTradeCollector()
    if args.mock:
        collector.api_key = "" # 강제 mock 모드

    res = collector.collect_all(days=args.days, max_workers=args.workers, reset=args.reset)
    print(f"=== 수집 결과 요약 ===")
    print(f"- 수집 건수: {res['total_collected']}")
    print(f"- 신규 저장: {res['new_inserted']}")
    print(f"- Parquet 내보내기: {res['exported']}")
    print(f"- Mock 모드 여부: {res['is_mock']}")

if __name__ == "__main__":
    main()

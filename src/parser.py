import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# 법정동 시군구 코드 캐싱
_LAWD_CACHE = None

def get_lawd_mapping() -> dict[str, str]:
    global _LAWD_CACHE
    if _LAWD_CACHE is None:
        lawd_path = Path(__file__).resolve().parent / "constants" / "lawd_cd.json"
        if lawd_path.exists():
            with open(lawd_path, "r", encoding="utf-8") as f:
                _LAWD_CACHE = json.load(f)
        else:
            _LAWD_CACHE = {}
    return _LAWD_CACHE

def split_sido_sgg(full_name: str) -> tuple[str, str]:
    """'서울특별시 종로구' -> ('서울특별시', '종로구'), '세종특별자치시' -> ('세종특별자치시', '세종특별자치시')"""
    parts = full_name.strip().split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name, full_name

def clean_amount(val: Any) -> int:
    """거래금액 문자열(' 12,500 ')을 정수(만원 단위, 12500)로 변환"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).replace(",", "").strip()
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else 0

def generate_deal_hash(deal_date: str, sgg_cd: str, umd_nm: str, apt_name: str,
                       exclusive_area: float, floor: int, deal_amount: int) -> str:
    """거래 건의 고유 식별 해시(SHA-256) 생성"""
    raw_key = f"{deal_date}|{sgg_cd}|{umd_nm}|{apt_name}|{exclusive_area:.2f}|{floor}|{deal_amount}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

def _parse_xml_items(xml_str: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_str)
        # body/items/item 경로 탐색
        for item_node in root.findall(".//item"):
            item_dict = {}
            for child in item_node:
                item_dict[child.tag] = child.text.strip() if child.text else ""
            items.append(item_dict)
    except Exception:
        pass
    return items

def parse_trade_items(raw_data: Any, target_start_date: str = "", default_sgg_cd: str = "") -> list[dict]:
    """
    공공데이터 API의 응답 데이터(XML 문자열, JSON 문자열, 딕셔너리, 리스트)를
    표준화된 정제 데이터 리스트로 변환하고 target_start_date 이후 계약 건만 필터링합니다.
    """
    lawd_map = get_lawd_mapping()
    raw_list: list[dict] = []

    if isinstance(raw_data, str):
        data_str = raw_data.strip()
        if data_str.startswith("<"):
            raw_list = _parse_xml_items(data_str)
        else:
            try:
                parsed = json.loads(data_str)
                if isinstance(parsed, list):
                    raw_list = parsed
                elif isinstance(parsed, dict):
                    # 공공데이터 JSON 구조 대응 (response.body.items.item 등)
                    items = (parsed.get("response", {})
                                   .get("body", {})
                                   .get("items", {})
                                   .get("item", []))
                    if isinstance(items, dict):
                        raw_list = [items]
                    elif isinstance(items, list):
                        raw_list = items
                    else:
                        raw_list = [parsed]
            except Exception:
                raw_list = []
    elif isinstance(raw_data, list):
        raw_list = raw_data
    elif isinstance(raw_data, dict):
        raw_list = [raw_data]

    results = []
    for item in raw_list:
        # 계약일자 구성
        try:
            year = int(item.get("dealYear") or item.get("년") or 0)
            month = int(item.get("dealMonth") or item.get("월") or 0)
            day = int(item.get("dealDay") or item.get("일") or 0)
            if year == 0 or month == 0 or day == 0:
                continue
            deal_date = f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            continue

        # 최근 7일(target_start_date) 이전 건은 필터링
        if target_start_date and deal_date < target_start_date:
            continue

        deal_amount = clean_amount(item.get("dealAmount") or item.get("거래금액"))
        if deal_amount <= 0:
            continue

        sgg_cd = str(item.get("sggCd") or item.get("지역코드") or default_sgg_cd).strip()
        umd_nm = str(item.get("umdNm") or item.get("법정동") or "").strip()
        apt_name = str(item.get("aptNm") or item.get("아파트") or "").strip()
        
        try:
            exclusive_area = float(item.get("excluUseAr") or item.get("전용면적") or 0.0)
        except (ValueError, TypeError):
            exclusive_area = 0.0

        try:
            floor = int(item.get("floor") or item.get("층") or 0)
        except (ValueError, TypeError):
            floor = 0

        try:
            build_year = int(item.get("buildYear") or item.get("건축년도") or 0)
        except (ValueError, TypeError):
            build_year = 0

        cancel_deal_type = str(item.get("cdealType") or item.get("해제여부") or "").strip()

        # 평형 및 평당가격 계산
        pyeong = round(exclusive_area / 3.30578, 1) if exclusive_area > 0 else 0.0
        price_per_pyeong = round(deal_amount / pyeong, 1) if pyeong > 0 else 0.0

        # 시도/시군구명 매핑
        full_loc_name = lawd_map.get(sgg_cd, "")
        sido_name, sgg_name = split_sido_sgg(full_loc_name) if full_loc_name else ("기타", "기타")

        deal_hash = generate_deal_hash(
            deal_date=deal_date,
            sgg_cd=sgg_cd,
            umd_nm=umd_nm,
            apt_name=apt_name,
            exclusive_area=exclusive_area,
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
            "exclusive_area": exclusive_area,
            "pyeong": pyeong,
            "floor": floor,
            "deal_amount": deal_amount,
            "price_per_pyeong": price_per_pyeong,
            "build_year": build_year,
            "cancel_deal_type": cancel_deal_type,
        })

    return results

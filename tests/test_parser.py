import pytest
from src.parser import clean_amount, generate_deal_hash, parse_trade_items

def test_clean_amount():
    assert clean_amount("  12,500 ") == 12500
    assert clean_amount("8,000") == 8000
    assert clean_amount(15000) == 15000
    assert clean_amount(None) == 0
    assert clean_amount("") == 0
    assert clean_amount("invalid") == 0

def test_generate_deal_hash():
    h1 = generate_deal_hash("2026-09-28", "11110", "사직동", "광화문풍림스페이스본", 94.51, 7, 125000)
    h2 = generate_deal_hash("2026-09-28", "11110", "사직동", "광화문풍림스페이스본", 94.51, 7, 125000)
    assert h1 == h2
    assert len(h1) == 64
    
    # 다른 값이면 해시가 달라야 함
    h3 = generate_deal_hash("2026-09-28", "11110", "사직동", "광화문풍림스페이스본", 94.51, 8, 125000)
    assert h1 != h3

def test_parse_trade_items_dict_input():
    mock_items = [
        {
            "dealYear": 2026, "dealMonth": 9, "dealDay": 28,
            "dealAmount": " 120,000", "sggCd": "11110", "umdNm": "사직동",
            "aptNm": "테스트아파트", "excluUseAr": 84.95, "floor": 10,
            "buildYear": 2020, "cdealType": ""
        },
        {
            # 대상 기간(2026-09-23) 이전 거래 (제외되어야 함)
            "dealYear": 2026, "dealMonth": 9, "dealDay": 20,
            "dealAmount": " 85,000", "sggCd": "11110", "umdNm": "사직동",
            "aptNm": "과거아파트", "excluUseAr": 59.9, "floor": 5,
            "buildYear": 2015, "cdealType": ""
        }
    ]
    items = parse_trade_items(mock_items, target_start_date="2026-09-23")
    assert len(items) == 1
    item = items[0]
    assert item["deal_date"] == "2026-09-28"
    assert item["deal_amount"] == 120000
    assert item["exclusive_area"] == 84.95
    assert item["pyeong"] == round(84.95 / 3.30578, 1)
    assert item["price_per_pyeong"] == round(120000 / item["pyeong"], 1)
    assert item["sgg_cd"] == "11110"
    assert item["sido_name"] == "서울특별시"
    assert item["sgg_name"] == "종로구"
    assert item["apt_name"] == "테스트아파트"
    assert len(item["deal_hash"]) == 64

def test_parse_trade_items_xml_input():
    xml_data = """<?xml version="1.0" encoding="UTF-8"?>
    <response>
      <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
      <body>
        <items>
          <item>
            <dealYear>2026</dealYear>
            <dealMonth>9</dealMonth>
            <dealDay>27</dealDay>
            <dealAmount> 95,000</dealAmount>
            <sggCd>41111</sggCd>
            <umdNm>파장동</umdNm>
            <aptNm>수원한일타운</aptNm>
            <excluUseAr>84.87</excluUseAr>
            <floor>12</floor>
            <buildYear>1999</buildYear>
            <cdealType></cdealType>
          </item>
        </items>
      </body>
    </response>
    """
    items = parse_trade_items(xml_data, target_start_date="2026-09-23")
    assert len(items) == 1
    assert items[0]["sido_name"] == "경기도"
    assert items[0]["sgg_name"] == "수원시 장안구"
    assert items[0]["apt_name"] == "수원한일타운"
    assert items[0]["deal_amount"] == 95000

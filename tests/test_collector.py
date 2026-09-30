from unittest.mock import patch, MagicMock
from src.collector import AptTradeCollector

def test_get_target_ym_list():
    collector = AptTradeCollector(api_key="mock_key")
    months = collector.get_target_ym_list(days=7)
    assert len(months) in [1, 2]
    for ym in months:
        assert len(ym) == 6
        assert ym.isdigit()

@patch("httpx.Client.get")
def test_fetch_sgg_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<response><header><resultCode>00</resultCode></header><body><items></items></body></response>"
    mock_get.return_value = mock_resp
    
    collector = AptTradeCollector(api_key="mock_key")
    result = collector.fetch_sgg("11110", "202609")
    assert result is not None
    assert "<response>" in result

def test_generate_mock_data():
    collector = AptTradeCollector(api_key="")
    mock_deals = collector.generate_mock_data(count=50, days=7)
    assert len(mock_deals) == 50
    assert "deal_hash" in mock_deals[0]
    assert "deal_date" in mock_deals[0]
    assert "deal_amount" in mock_deals[0]
    assert mock_deals[0]["deal_amount"] > 0
    assert mock_deals[0]["sido_name"] != ""

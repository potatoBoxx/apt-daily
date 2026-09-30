import logging
import os
from typing import Any
import httpx
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.storage import get_daily_summary, save_daily_summary, DEFAULT_DB_PATH
from src.dashboard.queries import get_daily_market_metrics

load_dotenv()
logger = logging.getLogger("analyzer")

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

def build_analyst_prompt(deal_date: str, metrics: dict) -> str:
    """
    특정 일자의 실거래 통계 지표를 바탕으로
    부동산 수석 애널리스트 페르소나의 분석 프롬프트를 구성합니다.
    """
    deal_count = metrics.get("deal_count", 0)
    avg_amount = metrics.get("avg_amount", 0)
    avg_pyeong_price = metrics.get("avg_pyeong_price", 0.0)
    max_amount = metrics.get("max_amount", 0)
    capital_ratio = metrics.get("capital_ratio", 0.0)
    top3_deals = metrics.get("top3_deals", [])
    size_dist = metrics.get("size_dist", {})

    top3_text = ""
    for idx, d in enumerate(top3_deals, 1):
        deal_amt = d.get('deal_amount') or 0
        pyeong_price = d.get('price_per_pyeong') or 0.0
        apt_nm = d.get('apt_name') or "단지"
        sido = d.get('sido_name') or ""
        sgg = d.get('sgg_name') or ""
        pyeong = d.get('pyeong') or "-"
        flr = d.get('floor') or "-"
        top3_text += f"{idx}. {apt_nm} ({sido} {sgg}, {pyeong}평, {flr}층) -> 거래금액: {deal_amt:,}만원 (평당 {pyeong_price:,}만원)\n"

    size_text = ", ".join([f"{k}: {v}건" for k, v in size_dist.items()]) if size_dist else "집계 없음"

    prompt = f"""
당신은 대한민국 부동산 시장 동향을 예리하게 분석하는 15년 경력의 '부동산 전문 수석 애널리스트'입니다.
아래 제공된 [{deal_date}] 하루 동안 전국에서 체결되어 등록된 아파트 매매 실거래가 통계를 분석하여, 투자자와 실수요자가 한눈에 시장 흐름을 파악할 수 있는 고품격 '일일 마켓 브리핑' 리포트를 작성해 주세요.

### [데이터 요약 - {deal_date}]
- 총 거래 건수: {deal_count:,}건
- 평균 거래금액: {avg_amount:,}만원
- 평균 평당가: {avg_pyeong_price:,}만원/평
- 최고 거래금액: {max_amount:,}만원
- 수도권(서울/경기/인천) 거래 비중: {capital_ratio}%
- 평형대별 거래 분포: {size_text}

### [당일 최고가 거래 TOP 3]
{top3_text}

---
### [작성 지침 및 출력 포맷]
반드시 다음 구조를 지켜 전문적이고 정제된 마크다운(Markdown) 포맷으로 작성해 주세요:

### 📌 [{deal_date}] 오늘의 아파트 마켓 브리핑
- **거래량 및 시장 체감**: (당일 거래 활성도 및 시장 체감 분위기 분석 1~2문장)
- **가격 및 평당가 흐름**: (평균 거래가 및 평당가 수준에 대한 가격대 평가 1~2문장)
- **지역별 쏠림 / 특이사항**: (수도권 비중 및 지방 거래 흐름에 대한 핵심 코멘트 1~2문장)

### 🏆 오늘의 주요 거래 & 화제 단지 TOP 3
(위 당일 최고가 거래 TOP 3 단지를 각각 1, 2, 3번으로 나누어, 거래 가격의 상징성, 해당 지역/단지의 입지적 가치 및 거래 의미를 애널리스트 관점에서 1~2줄씩 명쾌하게 코멘트해 주세요.)

### 💡 투자자 & 실수요자 관전 포인트
(현재의 거래량 및 가격대 흐름을 종합했을 때, 매수 대기자 및 투자자가 유의해서 지켜보아야 할 시장 시사점을 1~2문단으로 통찰력 있게 조언해 주세요.)
"""
    return prompt.strip()

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]

def call_gemini_api(prompt: str, api_key: str | None = None, model: str = DEFAULT_GEMINI_MODEL) -> str:
    """Google Gemini API를 호출하여 프롬프트에 대한 응답 텍스트를 생성합니다."""
    key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return "⚠️ `GEMINI_API_KEY`가 설정되지 않았습니다. `.env` 파일에 유효한 Gemini API 키를 등록해 주세요."

    # 모델 후보군 리스트: 지정된 모델 우선, 실패 시 fallback 모델 순차 시도
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
    last_error = ""

    for target_model in models_to_try:
        url = GEMINI_API_ENDPOINT.format(model=target_model)
        params = {"key": key}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096
            }
        }

        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(url, params=params, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    parts = data["candidates"][0]["content"]["parts"]
                    text = "".join([p.get("text", "") for p in parts]).strip()
                    if text:
                        return text
                elif resp.status_code in (404, 503):
                    logger.warning(f"모델 {target_model} 호출 실패 ({resp.status_code}): 다음 후보 모델 시도")
                    last_error = f"{target_model} ({resp.status_code}): {resp.text[:150]}"
                    continue
                else:
                    resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            last_error = str(e)
            if e.response.status_code in (404, 503):
                continue
            raise
        except Exception as e:
            last_error = str(e)
            logger.warning(f"모델 {target_model} 예외: {e}")
            continue

    return f"⚠️ Gemini AI 분석 생성 중 오류가 발생했습니다: {last_error}"

def is_error_summary(text: str) -> bool:
    """분석 결과 텍스트가 오류 메시지인지 판별합니다."""
    if not text:
        return True
    error_keywords = ["⚠️", "오류가 발생했습니다", "Client error", "Not Found", "404", "503", "UNAVAILABLE"]
    return any(kw in text for kw in error_keywords)

def get_or_create_daily_analysis(
    deal_date: str,
    parquet_path: str,
    db_path: str = DEFAULT_DB_PATH,
    api_key: str | None = None,
    force_refresh: bool = False,
    model: str = DEFAULT_GEMINI_MODEL
) -> tuple[dict, bool]:
    """
    특정 일자의 AI 분석 요약을 조회하거나 신규 생성합니다.
    - 캐시 히트 (정상 요약 존재 & force_refresh=False): SQLite에서 즉시 로드 (is_cached=True)
    - 캐시 미스 (미존재, force_refresh=True, 또는 기존 캐시가 오류인 경우): Gemini API 호출 (is_cached=False)
    """
    # 1. 캐시 확인 (오류가 아닌 유효한 분석 리포트만 캐시 히트로 인정)
    if not force_refresh:
        cached = get_daily_summary(deal_date, db_path=db_path)
        if cached:
            summary_text = cached.get("summary_markdown", "")
            if not is_error_summary(summary_text):
                return cached, True
            logger.info(f"[{deal_date}] 캐시된 요약에 오류 내용이 감지되어 자동으로 재분석을 수행합니다.")

    # 2. 통계 데이터 추출
    metrics = get_daily_market_metrics(parquet_path, deal_date)
    if metrics["deal_count"] == 0:
        empty_res = {
            "deal_date": deal_date,
            "summary_markdown": f"ℹ️ [{deal_date}]에는 등록된 실거래 데이터가 없어 분석 리포트를 생성할 수 없습니다.",
            "deal_count": 0,
            "avg_amount": 0,
            "max_amount": 0,
            "model_name": model
        }
        return empty_res, False

    # 3. Gemini 프롬프트 생성 및 API 호출
    prompt = build_analyst_prompt(deal_date, metrics)
    try:
        summary_text = call_gemini_api(prompt, api_key=api_key, model=model)
    except Exception as e:
        logger.error(f"Gemini API 호출 중 오류 발생: {e}")
        summary_text = f"⚠️ Gemini AI 분석 생성 중 오류가 발생했습니다: {str(e)}"

    stats = {
        "deal_count": metrics["deal_count"],
        "avg_amount": metrics["avg_amount"],
        "max_amount": metrics["max_amount"]
    }

    # 4. 유효한 분석 결과일 때만 SQLite 영구 저장 (오류는 저장하지 않고 화면에만 반환)
    if not is_error_summary(summary_text):
        save_daily_summary(
            deal_date=deal_date,
            summary_markdown=summary_text,
            stats=stats,
            model_name=model,
            db_path=db_path
        )
        return get_daily_summary(deal_date, db_path=db_path) or {
            "deal_date": deal_date,
            "summary_markdown": summary_text,
            **stats,
            "model_name": model
        }, False
    else:
        # 오류 발생 시에는 DB에 저장하지 않아 다음 호출 시 재시도 가능
        return {
            "deal_date": deal_date,
            "summary_markdown": summary_text,
            **stats,
            "model_name": model
        }, False


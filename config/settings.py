"""전역 설정값. 코드가 아니라 '설정'이므로 config/ 에 둔다."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --- 경로 -------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = ROOT_DIR / "config"
ENV_PATH = ROOT_DIR / ".env"
STOPWORDS_PATH = CONFIG_DIR / "stopwords_ko.txt"

load_dotenv(ENV_PATH, override=False)

# --- 네이버 API 플랫폼 선택 ----------------------------------------------
# .env 의 NAVER_API_PLATFORM 으로 전환.
#   apihub     : NAVER Cloud Platform / API Hub (naverapihub.apigw.ntruss.com)
#   developers : 기존 개발자센터 (openapi.naver.com)  * 2026-07-31 검색 API 종료 예정
NAVER_API_PLATFORM = (os.getenv("NAVER_API_PLATFORM") or "apihub").strip().lower()

_PLATFORMS: dict[str, dict] = {
    "apihub": {
        "search_base": "https://naverapihub.apigw.ntruss.com/search/v1",
        "trend_url": "https://naverapihub.apigw.ntruss.com/search-trend/v1/search",
        "header_id": "X-NCP-APIGW-API-KEY-ID",
        "header_secret": "X-NCP-APIGW-API-KEY",
        "use_format_param": True,
        "verticals": {
            "뉴스": "news", "블로그": "blog", "웹문서": "webkr", "이미지": "image",
            "지식iN": "kin", "지역": "local", "카페글": "cafearticle", "백과사전": "encyc",
        },
    },
    "developers": {
        "search_base": "https://openapi.naver.com/v1/search",
        "trend_url": "https://openapi.naver.com/v1/datalab/search",
        "header_id": "X-Naver-Client-Id",
        "header_secret": "X-Naver-Client-Secret",
        "use_format_param": False,
        "verticals": {
            "뉴스": "news.json", "블로그": "blog.json", "웹문서": "webkr.json",
            "이미지": "image", "지식iN": "kin.json", "지역": "local.json",
            "카페글": "cafearticle.json", "백과사전": "encyc.json",
        },
    },
}
_P = _PLATFORMS.get(NAVER_API_PLATFORM, _PLATFORMS["apihub"])

SEARCH_BASE_URL: str = _P["search_base"]
DATALAB_TREND_URL: str = _P["trend_url"]
AUTH_HEADER_ID: str = _P["header_id"]
AUTH_HEADER_SECRET: str = _P["header_secret"]
USE_FORMAT_PARAM: bool = _P["use_format_param"]
SEARCH_VERTICALS: dict[str, str] = _P["verticals"]

# 응답에 날짜 필드가 있어 기간 필터가 실제로 동작하는 버티컬
DATE_FILTERABLE = {"뉴스", "블로그"}
DATE_FIELD = {"뉴스": "pubDate", "블로그": "postdate"}

# --- 수집 파라미터 --------------------------------------------------------
DISPLAY_MAX = 100          # API 한도
START_MAX = 1000           # API 한도 (start + display - 1 <= 1000)
LOCAL_DISPLAY_MAX = 5      # 지역 검색은 최대 5건
DEFAULT_COLLECT_SIZE = 200
MAX_KEYWORDS_SEARCH = 10
MAX_KEYWORDS_TREND = 5
THREAD_WORKERS = 4
REQUEST_DELAY_SEC = 0.1
HTTP_TIMEOUT = 10
RETRY_BACKOFF_SEC = 2.0    # 429 시 1회 대기 후 재시도

# --- DataLab ------------------------------------------------------------
DATALAB_MIN_DATE = "2016-01-01"
DATALAB_DEVICES = {"전체": "", "PC": "pc", "모바일": "mo"}
DATALAB_GENDERS = {"전체": "", "남성": "m", "여성": "f"}
DATALAB_AGES = {
    "0~12세": "1", "13~18세": "2", "19~24세": "3", "25~29세": "4",
    "30~34세": "5", "35~39세": "6", "40~44세": "7", "45~49세": "8",
    "50~54세": "9", "55~59세": "10", "60세 이상": "11",
}

# --- 시각화 ------------------------------------------------------------
KOREA_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
]

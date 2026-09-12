"""네이버 검색 API + 데이터랩 검색어 트렌드 API 저수준 클라이언트.

공식 문서 기준:
- 검색:   GET https://openapi.naver.com/v1/search/{vertical}?query=&display=&start=&sort=
          헤더 X-Naver-Client-Id / X-Naver-Client-Secret
          display<=100, start<=1000, sort in {sim, date}
- 트렌드: POST https://openapi.naver.com/v1/datalab/search
          body: startDate, endDate, timeUnit, keywordGroups[], device, gender, ages[]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (  # noqa: E402
    AUTH_HEADER_ID,
    AUTH_HEADER_SECRET,
    DATALAB_TREND_URL,
    HTTP_TIMEOUT,
    RETRY_BACKOFF_SEC,
    SEARCH_BASE_URL,
    SEARCH_VERTICALS,
    USE_FORMAT_PARAM,
)
from src.credentials import Credentials  # noqa: E402


class NaverAPIError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class RateLimitError(NaverAPIError):
    pass


class NaverClient:
    def __init__(self, creds: Credentials):
        if not creds.is_complete:
            raise NaverAPIError("API 자격증명이 설정되지 않았습니다 (.env 확인).")
        self._headers = {
            AUTH_HEADER_ID: creds.client_id,
            AUTH_HEADER_SECRET: creds.client_secret,
        }
        self._session = requests.Session()

    # -- 내부 -------------------------------------------------------------
    def _request(self, method: str, url: str, *, retried: bool = False, **kw) -> dict:
        try:
            resp = self._session.request(
                method, url, headers=self._headers, timeout=HTTP_TIMEOUT, **kw
            )
        except requests.RequestException as exc:  # 네트워크 계열
            raise NaverAPIError(f"요청 실패: {exc}") from exc

        if resp.status_code == 429:
            if not retried:
                time.sleep(RETRY_BACKOFF_SEC)
                return self._request(method, url, retried=True, **kw)
            raise RateLimitError("호출 한도(429)를 초과했습니다.", status=429)

        if resp.status_code != 200:
            msg = resp.text[:300]
            raise NaverAPIError(f"HTTP {resp.status_code}: {msg}", status=resp.status_code)

        try:
            return resp.json()
        except ValueError as exc:
            raise NaverAPIError("응답 JSON 파싱 실패") from exc

    # -- 검색 -----------------------------------------------------------
    def search(
        self, vertical: str, query: str, *, display: int, start: int, sort: str = "sim"
    ) -> dict:
        """검색 8종 단일 페이지 조회. vertical 은 표시명('뉴스' 등)."""
        if vertical not in SEARCH_VERTICALS:
            raise NaverAPIError(f"알 수 없는 버티컬: {vertical}")
        path = SEARCH_VERTICALS[vertical]
        url = f"{SEARCH_BASE_URL}/{path}"
        params = {"query": query, "display": display, "start": start}
        if USE_FORMAT_PARAM:
            params["format"] = "json"
        # 지역/이미지 는 sort 값 체계가 다르므로 sim/date 만 안전하게 전달
        if sort in ("sim", "date"):
            params["sort"] = sort
        return self._request("GET", url, params=params)

    # -- 검색어 트렌드 -------------------------------------------------
    def search_trend(self, body: dict) -> dict:
        return self._request("POST", DATALAB_TREND_URL, json=body)

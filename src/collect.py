"""검색 8종 + 검색어 트렌드 수집 오케스트레이션.

- 검색어(콤마 구분) x 버티컬 을 ThreadPool 로 병렬 수집, 페이지네이션은 순차.
- 뉴스/블로그는 sort=date 로 당겨오며 기간 밖에 도달하면 조기 중단.
- 결과는 파라미터 해시 기준 parquet 로 캐시.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (  # noqa: E402
    CACHE_DIR,
    DATE_FIELD,
    DATE_FILTERABLE,
    DISPLAY_MAX,
    LOCAL_DISPLAY_MAX,
    REQUEST_DELAY_SEC,
    START_MAX,
    THREAD_WORKERS,
)
from src.naver_client import NaverAPIError, NaverClient, RateLimitError  # noqa: E402

_TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str | None) -> str:
    if not text:
        return ""
    return html.unescape(_TAG_RE.sub("", text)).strip()


def _domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except ValueError:
        return ""


def _parse_item_date(vertical: str, item: dict) -> pd.Timestamp | None:
    field_name = DATE_FIELD.get(vertical)
    raw = item.get(field_name) if field_name else None
    if not raw:
        return None
    try:
        if vertical == "뉴스":
            return pd.Timestamp(parsedate_to_datetime(raw)).tz_localize(None)
        if vertical == "블로그":
            return pd.Timestamp(datetime.strptime(raw, "%Y%m%d"))
    except (TypeError, ValueError):
        return None
    return None


def _source_of(vertical: str, item: dict) -> str:
    if vertical == "블로그":
        return item.get("bloggername", "") or _domain(item.get("bloggerlink"))
    if vertical == "카페글":
        return item.get("cafename", "")
    if vertical == "지역":
        return item.get("category", "")
    if vertical == "이미지":
        return _domain(item.get("link"))
    return _domain(item.get("originallink") or item.get("link"))


@dataclass
class VerticalStatus:
    keyword: str
    vertical: str
    ok: bool = True
    count: int = 0
    total_available: int | None = None
    message: str = ""
    truncated_by_period: bool = False


@dataclass
class CollectResult:
    df: pd.DataFrame
    statuses: list[VerticalStatus] = field(default_factory=list)
    from_cache: bool = False


_CACHE_VERSION = 2  # _normalize 스키마 변경 시 올린다 (기존 캐시 자동 무효화)


# --------------------------------------------------------------------------
def _cache_key(keywords, verticals, size, start_d, end_d) -> str:
    payload = json.dumps(
        {
            "ver": _CACHE_VERSION,
            "kw": sorted(keywords),
            "v": sorted(verticals),
            "size": size,
            "start": str(start_d),
            "end": str(end_d),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"search_{key}.parquet"


# --------------------------------------------------------------------------
def _collect_one(
    client: NaverClient,
    vertical: str,
    keyword: str,
    size: int,
    start_d: date | None,
    end_d: date | None,
) -> tuple[list[dict], VerticalStatus]:
    status = VerticalStatus(keyword=keyword, vertical=vertical)
    per_page = LOCAL_DISPLAY_MAX if vertical == "지역" else DISPLAY_MAX
    hard_cap = LOCAL_DISPLAY_MAX if vertical == "지역" else min(size, START_MAX)
    date_filter = vertical in DATE_FILTERABLE and start_d is not None and end_d is not None
    sort = "date" if date_filter else "sim"

    start_ts = pd.Timestamp(start_d) if start_d else None
    end_ts = pd.Timestamp(end_d) + pd.Timedelta(days=1) if end_d else None

    rows: list[dict] = []
    start = 1
    try:
        while start <= START_MAX and len(rows) < hard_cap:
            display = min(per_page, hard_cap - len(rows), START_MAX - start + 1)
            if display <= 0:
                break
            data = client.search(vertical, keyword, display=display, start=start, sort=sort)
            status.total_available = data.get("total")
            items = data.get("items", []) or []
            if not items:
                break

            stop = False
            for it in items:
                ts = _parse_item_date(vertical, it)
                if date_filter and ts is not None:
                    if ts < start_ts:
                        stop = True
                        continue
                    if ts >= end_ts:
                        continue
                rows.append(_normalize(vertical, keyword, it, ts))

            if stop:
                status.truncated_by_period = False
                break
            if len(items) < display:
                break
            start += display
            time.sleep(REQUEST_DELAY_SEC)
        else:
            # while 조건으로 빠져나옴 (한도 도달)
            if date_filter and start > START_MAX:
                status.truncated_by_period = True

        status.count = len(rows)
    except RateLimitError as exc:
        status.ok = False
        status.message = str(exc)
    except NaverAPIError as exc:
        status.ok = False
        status.message = str(exc)
    return rows, status


def _to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize(vertical: str, keyword: str, item: dict, ts: pd.Timestamp | None) -> dict:
    return {
        "keyword": keyword,
        "vertical": vertical,
        "title": strip_tags(item.get("title")),
        "description": strip_tags(item.get("description")),
        "link": item.get("link", ""),
        "source": _source_of(vertical, item),
        "domain": _domain(item.get("originallink") or item.get("link")),
        "date": ts,
        "thumbnail": item.get("thumbnail", ""),
        "address": item.get("address", ""),
        "road_address": item.get("roadAddress", ""),
        "category": item.get("category", ""),
        "telephone": item.get("telephone", ""),
        "mapx": item.get("mapx", ""),
        "mapy": item.get("mapy", ""),
        "img_width": _to_int(item.get("sizewidth")),
        "img_height": _to_int(item.get("sizeheight")),
        "raw_pubdate": item.get(DATE_FIELD.get(vertical, ""), ""),
    }


# --------------------------------------------------------------------------
def collect_search(
    client: NaverClient,
    keywords: list[str],
    verticals: list[str],
    size: int,
    start_d: date | None,
    end_d: date | None,
    *,
    use_cache: bool = True,
    progress_cb=None,
) -> CollectResult:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(keywords, verticals, size, start_d, end_d)
    cpath = _cache_path(key)

    if use_cache and cpath.exists():
        df = pd.read_parquet(cpath)
        meta_path = cpath.with_suffix(".status.json")
        statuses = []
        if meta_path.exists():
            statuses = [VerticalStatus(**s) for s in json.loads(meta_path.read_text("utf-8"))]
        return CollectResult(df=df, statuses=statuses, from_cache=True)

    jobs = [(v, k) for k in keywords for v in verticals]
    all_rows: list[dict] = []
    statuses: list[VerticalStatus] = []
    done = 0

    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as pool:
        futs = {
            pool.submit(_collect_one, client, v, k, size, start_d, end_d): (v, k)
            for v, k in jobs
        }
        for fut in as_completed(futs):
            rows, status = fut.result()
            all_rows.extend(rows)
            statuses.append(status)
            done += 1
            if progress_cb:
                progress_cb(done, len(jobs), status)

    cols = [
        "keyword", "vertical", "title", "description", "link", "source", "domain",
        "date", "thumbnail", "address", "road_address", "category", "telephone",
        "mapx", "mapy", "img_width", "img_height", "raw_pubdate",
    ]
    df = pd.DataFrame(all_rows, columns=cols)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df.to_parquet(cpath, index=False)
    cpath.with_suffix(".status.json").write_text(
        json.dumps([s.__dict__ for s in statuses], ensure_ascii=False), "utf-8"
    )
    return CollectResult(df=df, statuses=statuses, from_cache=False)


# --------------------------------------------------------------------------
def collect_trend(
    client: NaverClient,
    keywords: list[str],
    start_d: date,
    end_d: date,
    time_unit: str,
    device: str,
    gender: str,
    ages: list[str],
) -> pd.DataFrame:
    """검색어 트렌드. 각 검색어 = 별도 그룹."""
    groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords[:5]]
    body: dict = {
        "startDate": start_d.isoformat(),
        "endDate": end_d.isoformat(),
        "timeUnit": time_unit,
        "keywordGroups": groups,
    }
    if device:
        body["device"] = device
    if gender:
        body["gender"] = gender
    if ages:
        body["ages"] = ages

    data = client.search_trend(body)
    frames = []
    for series in data.get("results", []):
        name = series.get("title", "")
        sdf = pd.DataFrame(series.get("data", []))
        if sdf.empty:
            continue
        sdf["keyword"] = name
        sdf["period"] = pd.to_datetime(sdf["period"])
        frames.append(sdf)
    if not frames:
        return pd.DataFrame(columns=["period", "ratio", "keyword"])
    return pd.concat(frames, ignore_index=True)[["period", "ratio", "keyword"]]

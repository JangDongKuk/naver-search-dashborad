"""네이버 지역 검색의 mapx/mapy 좌표를 WGS84 (경도/위도) 로 변환.

현재 네이버 지역 검색 API 는 mapx/mapy 를 'WGS84 경위도 * 1e7' 정수 문자열로 준다
(예: mapx="1270642050" -> 127.0642050). 과거 KATECH(TM128) 응답 호환을 위해
값의 크기로 형식을 추정한다.
"""
from __future__ import annotations

# 대한민국 대략 경위도 범위 (sanity check 용)
LON_RANGE = (124.0, 132.0)
LAT_RANGE = (33.0, 39.5)


def _to_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_coord(mapx: str | float | None, mapy: str | float | None) -> tuple[float, float] | None:
    """(lon, lat) 반환. 변환 실패 또는 범위 밖이면 None."""
    x = _to_float(mapx)
    y = _to_float(mapy)
    if x is None or y is None:
        return None

    # WGS84 * 1e7 형식 (현재 API)
    lon, lat = x / 1e7, y / 1e7
    if LON_RANGE[0] <= lon <= LON_RANGE[1] and LAT_RANGE[0] <= lat <= LAT_RANGE[1]:
        return lon, lat

    # 이미 경위도 그대로인 경우
    if LON_RANGE[0] <= x <= LON_RANGE[1] and LAT_RANGE[0] <= y <= LAT_RANGE[1]:
        return x, y

    return None

"""문서 단위 수치 피처 엔지니어링.

텍스트형 버티컬(뉴스·블로그·카페글·웹문서·지식iN·백과사전)의 각 문서에 대해
길이·토큰·명사·검색어 포함 여부·날짜 파생값을 계산한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.eda import _kiwi  # noqa: E402

_WS = re.compile(r"\s+")
_DOW_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 문서 길이(제목/본문 문자 수) 3분위 구간 라벨
LENGTH_BINS_LABELS = ["단문", "중문", "장문"]


def _word_count(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return 0
    return len(_WS.split(text))


def _noun_counts(texts: list[str]) -> list[int]:
    kiwi = _kiwi()
    out = []
    for tokens in kiwi.tokenize(list(texts)):
        out.append(sum(1 for t in tokens if t.tag in ("NNG", "NNP")))
    return out


def add_text_features(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """텍스트형 문서 DataFrame 에 피처 컬럼을 추가해 새 DataFrame 을 반환."""
    if df.empty:
        return df.copy()
    out = df.copy().reset_index(drop=True)
    title = out["title"].fillna("")
    desc = out["description"].fillna("")

    out["title_len"] = title.str.len()
    out["desc_len"] = desc.str.len()
    out["title_words"] = title.map(_word_count)
    out["desc_words"] = desc.map(_word_count)
    out["title_nouns"] = _noun_counts(title.tolist())
    out["desc_nouns"] = _noun_counts(desc.tolist())

    # 검색어 포함 여부 / 제목 내 위치 (문서의 keyword 컬럼 기준)
    def _contains(row_text: str, kw: str) -> bool:
        return kw.lower() in (row_text or "").lower()

    out["kw_in_title"] = [
        _contains(t, k) for t, k in zip(title.tolist(), out["keyword"].tolist())
    ]
    out["kw_in_desc"] = [
        _contains(d, k) for d, k in zip(desc.tolist(), out["keyword"].tolist())
    ]
    out["kw_pos_title"] = [
        (t.lower().find(k.lower()) if isinstance(t, str) else -1)
        for t, k in zip(title.tolist(), out["keyword"].tolist())
    ]

    out["is_naver_domain"] = out["domain"].fillna("").str.endswith("naver.com")

    # 날짜 파생
    dt = pd.to_datetime(out["date"], errors="coerce")
    out["date"] = dt
    out["pub_date"] = dt.dt.date
    out["pub_dow"] = dt.dt.dayofweek.map(
        lambda i: _DOW_KO[int(i)] if pd.notna(i) else None
    )
    out["pub_dow_num"] = dt.dt.dayofweek
    out["pub_week"] = dt.dt.to_period("W").astype(str).where(dt.notna(), None)
    out["pub_hour"] = dt.dt.hour
    out["pub_month"] = dt.dt.to_period("M").astype(str).where(dt.notna(), None)

    return out


def add_length_bins(df: pd.DataFrame, column: str = "title_len") -> pd.DataFrame:
    """길이 컬럼을 3분위(단문/중문/장문)로 나눈 <column>_bin 컬럼 추가."""
    out = df.copy()
    series = out[column]
    if series.nunique(dropna=True) < 3:
        out[f"{column}_bin"] = pd.Categorical(
            ["중문"] * len(out), categories=LENGTH_BINS_LABELS, ordered=True
        )
        return out
    try:
        out[f"{column}_bin"] = pd.qcut(
            series, q=3, labels=LENGTH_BINS_LABELS, duplicates="drop"
        )
    except ValueError:
        out[f"{column}_bin"] = pd.cut(series, bins=3, labels=LENGTH_BINS_LABELS)
    return out


NUMERIC_FEATURES = [
    "title_len", "desc_len", "title_words", "desc_words", "title_nouns", "desc_nouns",
]
NUMERIC_FEATURE_LABELS = {
    "title_len": "제목 길이(자)",
    "desc_len": "본문 길이(자)",
    "title_words": "제목 어절 수",
    "desc_words": "본문 어절 수",
    "title_nouns": "제목 명사 수",
    "desc_nouns": "본문 명사 수",
    "kw_pos_title": "제목 내 검색어 위치",
}

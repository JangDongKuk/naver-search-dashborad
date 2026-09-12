"""규칙 기반 인사이트 요약. LLM 호출 없음."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.viz import pct  # noqa: E402


def _top_share(series: pd.Series) -> tuple[str, float] | None:
    s = series[series.astype(str).str.len() > 0]
    if s.empty:
        return None
    vc = s.value_counts()
    return str(vc.index[0]), pct(vc.iloc[0], len(s))


def text_vertical_insights(
    df: pd.DataFrame, vertical: str, has_date: bool, test_notes: list[str]
) -> list[str]:
    out: list[str] = []
    n = len(df)
    out.append(f"**{vertical}** 문서 {n:,}건 · 검색어 {df['keyword'].nunique()}개 · 고유 도메인 {df['domain'].replace('', pd.NA).nunique()}개.")

    kw_share = _top_share(df["keyword"])
    if kw_share and df["keyword"].nunique() > 1:
        out.append(f"문서가 가장 많은 검색어는 **{kw_share[0]}** (전체의 {kw_share[1]}%).")

    dom = _top_share(df["domain"])
    if dom:
        out.append(f"최다 출처 도메인은 `{dom[0]}` ({dom[1]}%).")

    if "title_len" in df and df["keyword"].nunique() > 1:
        means = df.groupby("keyword")["title_len"].mean().sort_values(ascending=False)
        if len(means) >= 2 and means.iloc[-1] > 0:
            ratio = means.iloc[0] / means.iloc[-1]
            if ratio >= 1.15:
                out.append(
                    f"**{means.index[0]}** 의 평균 제목 길이가 **{means.index[-1]}** 보다 "
                    f"{ratio:.1f}배 깁니다."
                )

    if has_date and df["date"].notna().any():
        by_day = df.dropna(subset=["date"]).groupby(df["date"].dt.date).size()
        if not by_day.empty:
            peak = by_day.idxmax()
            out.append(f"게시량 피크는 **{peak}** ({by_day.max():,}건).")

    for note in test_notes:
        if "유의함" in note:
            out.append("통계 검정: " + note)

    return out


def local_insights(df: pd.DataFrame) -> list[str]:
    out = [f"지역 결과 {len(df):,}건 · 검색어 {df['keyword'].nunique()}개."]
    cat = _top_share(df["category"])
    if cat:
        out.append(f"가장 흔한 업종은 **{cat[0]}** ({cat[1]}%).")
    tel = pct(df["telephone"].astype(str).str.len().gt(0).sum(), len(df))
    out.append(f"전화번호 보유율 {tel}%.")
    return out


def image_insights(df: pd.DataFrame) -> list[str]:
    out = [f"이미지 결과 {len(df):,}건."]
    valid = df.dropna(subset=["img_width", "img_height"])
    if not valid.empty:
        land = pct((valid["img_width"] > valid["img_height"]).sum(), len(valid))
        out.append(
            f"해상도 정보가 있는 {len(valid):,}건 중 가로형이 {land}%, "
            f"평균 {valid['img_width'].mean():.0f}×{valid['img_height'].mean():.0f}."
        )
    dom = _top_share(df["domain"])
    if dom:
        out.append(f"최다 출처는 `{dom[0]}` ({dom[1]}%).")
    return out


def cross_vertical_insights(df: pd.DataFrame) -> list[str]:
    out = [
        f"전체 {len(df):,}건 · 버티컬 {df['vertical'].nunique()}종 · 검색어 {df['keyword'].nunique()}개."
    ]
    vc = df["vertical"].value_counts()
    if not vc.empty:
        out.append(f"수집량이 가장 많은 버티컬은 **{vc.index[0]}** ({pct(vc.iloc[0], len(df))}%).")
    dated = df["date"].notna().mean() * 100 if "date" in df else 0
    out.append(f"날짜 정보 보유 문서 비율 {dated:.0f}% (뉴스·블로그만 해당).")
    return out

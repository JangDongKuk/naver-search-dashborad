"""수집 결과 + 핵심 통계표를 하나의 .xlsx 로 묶어 내보낸다."""
from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import features, stats_tests  # noqa: E402


def _safe_sheet(name: str) -> str:
    for ch in r"[]:*?/\\":
        name = name.replace(ch, "_")
    return name[:31]


def build_excel(df: pd.DataFrame, trend_df: pd.DataFrame, cfg: dict, statuses: list) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        # 요약
        summary = pd.DataFrame(
            {
                "항목": ["검색어", "기간", "버티컬·검색어당 최대", "총 문서 수", "생성일"],
                "값": [
                    ", ".join(cfg.get("keywords", [])),
                    f'{cfg.get("start_d")} ~ {cfg.get("end_d")}',
                    cfg.get("size"),
                    len(df),
                    date.today().isoformat(),
                ],
            }
        )
        summary.to_excel(xw, sheet_name="요약", index=False)

        if statuses:
            pd.DataFrame(
                [
                    {"검색어": s.keyword, "버티컬": s.vertical,
                     "성공": s.ok, "수집": s.count, "API총건수": s.total_available,
                     "기간미충족": s.truncated_by_period, "메시지": s.message}
                    for s in statuses
                ]
            ).to_excel(xw, sheet_name="수집상태", index=False)

        for v in sorted(df["vertical"].unique()):
            sub = df[df["vertical"] == v].copy()
            sub.to_excel(xw, sheet_name=_safe_sheet(f"{v}_원본"), index=False)

            if v in ("뉴스", "블로그", "카페글", "웹문서", "지식iN", "백과사전"):
                try:
                    feat = features.add_text_features(sub, cfg.get("keywords", []))
                    stats_tests.describe_plus(
                        feat, features.NUMERIC_FEATURES, features.NUMERIC_FEATURE_LABELS
                    ).to_excel(xw, sheet_name=_safe_sheet(f"{v}_기술통계"))
                    feat.groupby("keyword").agg(
                        문서수=("title", "count"),
                        평균_제목길이=("title_len", "mean"),
                        평균_본문길이=("desc_len", "mean"),
                        고유도메인=("domain", pd.Series.nunique),
                    ).round(2).to_excel(xw, sheet_name=_safe_sheet(f"{v}_검색어피봇"))
                except Exception:  # noqa: BLE001 - 내보내기는 부분 실패 허용
                    pass

        if trend_df is not None and not trend_df.empty:
            trend_df.pivot_table(index="period", columns="keyword", values="ratio").to_excel(
                xw, sheet_name="검색어트렌드"
            )

    buf.seek(0)
    return buf.getvalue()

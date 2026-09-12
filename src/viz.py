"""플롯 공통 설정: 색맹 안전 팔레트, plotly 기본값, 헬퍼.

- 범주형: Carto 'Safe' (색각이상 대응, 고정 순서·순환 금지)
- 순차형(히트맵): 'Viridis' (지각 균일, CVD 친화)
- 파이/도넛/선버스트는 사용하지 않는다.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px

# Carto Safe – 색각이상 대응 범주형 팔레트 (고정 순서)
CATEGORICAL = [
    "#88CCEE", "#CC6677", "#DDCC77", "#117733", "#332288",
    "#AA4499", "#44AA99", "#999933", "#882255", "#661100",
]
SEQUENTIAL = "Viridis"

# plotly express 전역 기본값
px.defaults.color_discrete_sequence = CATEGORICAL
px.defaults.template = "plotly"


def color_map(keys) -> dict:
    """엔티티→색 고정 매핑. 필터로 계열 수가 바뀌어도 색이 유지되도록 한다."""
    keys = list(dict.fromkeys(keys))
    return {k: CATEGORICAL[i % len(CATEGORICAL)] for i, k in enumerate(keys)}


def apply_layout(fig, *, height: int = 380, legend_bottom: bool = True):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=48, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0)
        if legend_bottom
        else {},
        bargap=0.18,
    )
    for tr in fig.data:
        if tr.type in ("bar", "histogram"):
            tr.marker.line.width = 0
    return fig


def pct(part, whole) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def share_table(df: pd.DataFrame, column: str, n: int = 15, by: str | None = None) -> pd.DataFrame:
    """상위 값 표 + 비중(%). by 를 주면 by 별 분해 컬럼도 추가."""
    sub = df[df[column].astype(str).str.len() > 0]
    if sub.empty:
        return pd.DataFrame()
    total = len(sub)
    vc = sub[column].value_counts().head(n)
    out = pd.DataFrame({column: vc.index, "건수": vc.to_numpy()})
    out["비중(%)"] = out["건수"].map(lambda c: pct(c, total))
    if by and by in sub.columns:
        piv = pd.crosstab(sub[column], sub[by])
        piv = piv.loc[[v for v in out[column] if v in piv.index]]
        out = out.merge(piv.reset_index(), on=column, how="left")
    return out.reset_index(drop=True)

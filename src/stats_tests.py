"""기술통계 + 추론통계(scipy) 래퍼. 모두 tidy DataFrame + 해석 문구를 반환."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05


def _sig(p: float) -> str:
    if pd.isna(p):
        return "판정 불가"
    return "유의함 (p<0.05)" if p < ALPHA else "유의하지 않음"


def describe_plus(df: pd.DataFrame, columns: list[str], labels: dict | None = None) -> pd.DataFrame:
    """describe() + 왜도 + 첨도 + 결측 수."""
    labels = labels or {}
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return pd.DataFrame()
    base = df[cols].describe().T
    base["결측"] = df[cols].isna().sum()
    base["왜도"] = df[cols].skew(numeric_only=True)
    base["첨도"] = df[cols].kurtosis(numeric_only=True)
    base = base.rename(
        columns={
            "count": "n", "mean": "평균", "std": "표준편차", "min": "최소",
            "25%": "Q1", "50%": "중앙값", "75%": "Q3", "max": "최대",
        }
    )
    base.index = [labels.get(c, c) for c in base.index]
    ordered = ["n", "평균", "표준편차", "최소", "Q1", "중앙값", "Q3", "최대", "왜도", "첨도", "결측"]
    return base[[c for c in ordered if c in base.columns]].round(2)


def chi_square(df: pd.DataFrame, row: str, col: str) -> tuple[pd.DataFrame, str]:
    """행×열 범주 독립성 카이제곱 검정. (교차표, 해석문) 반환."""
    ct = pd.crosstab(df[row], df[col])
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        return ct, "범주가 부족해 검정을 수행할 수 없습니다."
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    n = ct.to_numpy().sum()
    min_dim = min(ct.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * min_dim)) if n and min_dim else np.nan
    strength = (
        "약한" if cramers_v < 0.2 else "중간" if cramers_v < 0.4 else "강한"
    )
    msg = (
        f"χ²={chi2:.1f}, dof={dof}, p={p:.4f} → {_sig(p)}. "
        f"Cramér's V={cramers_v:.3f} ({strength} 연관성)."
    )
    return ct, msg


def kruskal_by_group(df: pd.DataFrame, value: str, group: str) -> tuple[pd.DataFrame, str]:
    """그룹 간 분포 차이 Kruskal–Wallis 검정 (비모수 일원분산분석). (그룹 요약, 해석문)."""
    sub = df[[value, group]].dropna()
    groups = [g[value].to_numpy() for _, g in sub.groupby(group) if len(g) >= 2]
    summary = (
        sub.groupby(group)[value]
        .agg(n="count", 평균="mean", 중앙값="median", 표준편차="std")
        .round(2)
        .reset_index()
    )
    if len(groups) < 2:
        return summary, "그룹이 2개 미만이라 검정을 수행할 수 없습니다."
    h, p = stats.kruskal(*groups)
    return summary, f"H={h:.2f}, p={p:.4f} → 그룹 간 '{value}' 분포 차이 {_sig(p)}."


def mann_whitney(df: pd.DataFrame, value: str, group: str) -> str:
    sub = df[[value, group]].dropna()
    levels = sub[group].unique()
    if len(levels) != 2:
        return ""
    a = sub.loc[sub[group] == levels[0], value]
    b = sub.loc[sub[group] == levels[1], value]
    if len(a) < 2 or len(b) < 2:
        return ""
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    return f"Mann–Whitney U={u:.0f}, p={p:.4f} ({levels[0]} vs {levels[1]}) → {_sig(p)}."


def spearman(df: pd.DataFrame, a: str, b: str) -> str:
    sub = df[[a, b]].dropna()
    if len(sub) < 3:
        return "표본이 부족합니다."
    rho, p = stats.spearmanr(sub[a], sub[b])
    direction = "양" if rho > 0 else "음"
    return f"Spearman ρ={rho:.3f}, p={p:.4f} → {direction}의 상관, {_sig(p)}."


def correlation_matrix(df: pd.DataFrame, columns: list[str], labels: dict | None = None) -> pd.DataFrame:
    labels = labels or {}
    cols = [c for c in columns if c in df.columns]
    corr = df[cols].corr(method="spearman").round(2)
    corr.index = [labels.get(c, c) for c in corr.index]
    corr.columns = [labels.get(c, c) for c in corr.columns]
    return corr


def test_summary_table(rows: list[dict]) -> pd.DataFrame:
    """[{'검정': ..., '대상': ..., '통계량': ..., 'p값': ..., '해석': ...}] → DataFrame."""
    return pd.DataFrame(rows, columns=["검정", "대상", "통계량", "p값", "해석"])

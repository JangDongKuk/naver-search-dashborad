"""수집 데이터에 대한 기본 EDA: 집계 + 한국어 키워드 추출 + 워드클라우드."""
from __future__ import annotations

import sys
from collections import Counter
from functools import lru_cache
from itertools import combinations
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import KOREA_FONT_CANDIDATES, STOPWORDS_PATH  # noqa: E402


@lru_cache(maxsize=1)
def load_stopwords() -> frozenset[str]:
    if not STOPWORDS_PATH.exists():
        return frozenset()
    words = set()
    for line in STOPWORDS_PATH.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line)
    return frozenset(words)


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi

    return Kiwi()


@lru_cache(maxsize=1)
def korean_font_path() -> str | None:
    for p in KOREA_FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def extract_nouns(texts: list[str], extra_stop: set[str] | None = None) -> Counter:
    """명사(NNG/NNP) 카운터. 2글자 이상, 불용어 제외."""
    stop = set(load_stopwords())
    if extra_stop:
        stop |= {s.lower() for s in extra_stop}
    kiwi = _kiwi()
    counter: Counter = Counter()
    for tokens in kiwi.tokenize(list(texts)):
        for tok in tokens:
            if tok.tag in ("NNG", "NNP") and len(tok.form) >= 2:
                form = tok.form
                if form.lower() in stop:
                    continue
                counter[form] += 1
    return counter


def noun_lists(texts: list[str], extra_stop: set[str] | None = None) -> list[list[str]]:
    stop = set(load_stopwords())
    if extra_stop:
        stop |= {s.lower() for s in extra_stop}
    kiwi = _kiwi()
    out = []
    for tokens in kiwi.tokenize(list(texts)):
        forms = [
            t.form for t in tokens
            if t.tag in ("NNG", "NNP") and len(t.form) >= 2 and t.form.lower() not in stop
        ]
        out.append(forms)
    return out


def cooccurrence(texts: list[str], extra_stop: set[str] | None = None, top: int = 20) -> pd.DataFrame:
    pair_counter: Counter = Counter()
    for forms in noun_lists(texts, extra_stop):
        uniq = sorted(set(forms))
        for a, b in combinations(uniq, 2):
            pair_counter[(a, b)] += 1
    rows = [
        {"키워드 A": a, "키워드 B": b, "동시 출현": c}
        for (a, b), c in pair_counter.most_common(top)
    ]
    return pd.DataFrame(rows)


def cooccurrence_matrix(
    texts: list[str], extra_stop: set[str] | None = None, top_terms: int = 15
) -> pd.DataFrame:
    """상위 명사 top_terms 개에 대한 문서 단위 동시출현 대칭 행렬."""
    doc_forms = [set(f) for f in noun_lists(texts, extra_stop)]
    freq: Counter = Counter()
    for forms in doc_forms:
        freq.update(forms)
    terms = [t for t, _ in freq.most_common(top_terms)]
    if not terms:
        return pd.DataFrame()
    mat = pd.DataFrame(0, index=terms, columns=terms, dtype=int)
    for forms in doc_forms:
        present = [t for t in terms if t in forms]
        for a, b in combinations(present, 2):
            mat.loc[a, b] += 1
            mat.loc[b, a] += 1
    for t in terms:
        mat.loc[t, t] = freq[t]
    return mat


def keyword_noun_sets(
    df: pd.DataFrame, group_col: str, extra_stop: set[str] | None = None, top_terms: int = 60
) -> dict[str, set[str]]:
    """group_col(검색어 또는 버티컬)별 상위 명사 집합."""
    out: dict[str, set[str]] = {}
    for key, sub in df.groupby(group_col):
        texts = (sub["title"].fillna("") + " " + sub["description"].fillna("")).tolist()
        counter = extract_nouns(texts, extra_stop)
        out[str(key)] = {t for t, _ in counter.most_common(top_terms)}
    return out


def jaccard_matrix(sets: dict[str, set[str]]) -> pd.DataFrame:
    """집합 딕셔너리 → 자카드 유사도 대칭 행렬."""
    keys = list(sets)
    mat = pd.DataFrame(0.0, index=keys, columns=keys)
    for a in keys:
        for b in keys:
            sa, sb = sets[a], sets[b]
            union = sa | sb
            mat.loc[a, b] = round(len(sa & sb) / len(union), 3) if union else 0.0
    return mat


def tf_by_group(
    df: pd.DataFrame, group_col: str, extra_stop: set[str] | None = None, top_n: int = 25
) -> pd.DataFrame:
    """전역 상위 명사 × 그룹별 출현 빈도 + 편중도(최대 그룹 비중)."""
    groups = sorted(df[group_col].dropna().unique().tolist())
    per_group = {
        g: extract_nouns(
            (df.loc[df[group_col] == g, "title"].fillna("") + " "
             + df.loc[df[group_col] == g, "description"].fillna("")).tolist(),
            extra_stop,
        )
        for g in groups
    }
    total: Counter = Counter()
    for c in per_group.values():
        total.update(c)
    rows = []
    for term, tot in total.most_common(top_n):
        row = {"키워드": term, "전체": tot}
        counts = {g: per_group[g].get(term, 0) for g in groups}
        row.update(counts)
        row["편중도"] = round(max(counts.values()) / tot, 2) if tot else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def volume_timeseries(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """날짜가 있는 행만 대상으로 기간별 게시량."""
    sub = df.dropna(subset=["date"])
    if sub.empty:
        return pd.DataFrame(columns=["date", "keyword", "vertical", "count"])
    g = (
        sub.groupby([pd.Grouper(key="date", freq=freq), "keyword", "vertical"])
        .size()
        .reset_index(name="count")
    )
    return g


def top_values(df: pd.DataFrame, column: str, n: int = 15) -> pd.DataFrame:
    sub = df[df[column].astype(str).str.len() > 0]
    if sub.empty:
        return pd.DataFrame(columns=[column, "count"])
    return (
        sub[column].value_counts().head(n).rename_axis(column).reset_index(name="count")
    )


def summary_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["keyword", "vertical", "count"])
    return df.groupby(["keyword", "vertical"]).size().reset_index(name="count")


def make_wordcloud_figure(counter: Counter, max_words: int = 120):
    import matplotlib.pyplot as plt
    from wordcloud import WordCloud

    if not counter:
        return None
    wc = WordCloud(
        font_path=korean_font_path(),
        width=1000,
        height=500,
        background_color="white",
        max_words=max_words,
        colormap="viridis",
    ).generate_from_frequencies(dict(counter.most_common(max_words * 2)))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    fig.tight_layout(pad=0)
    return fig

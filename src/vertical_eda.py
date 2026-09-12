"""버티컬별 심층 EDA 렌더러 (Streamlit).

- 텍스트형 6종(뉴스·블로그·카페글·웹문서·지식iN·백과사전): render_text_vertical
- 지역: render_local
- 이미지: render_image
- 전역 교차분석: render_cross_vertical

각 페이지는 파이차트를 쓰지 않고 그래프 5개 이상 + 통계표 5개 이상을 제공한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import eda, features, stats_tests  # noqa: E402
from src import insights as ins  # noqa: E402
from src import viz  # noqa: E402

# --------------------------------------------------------------------------
VERTICAL_SPEC: dict[str, dict] = {
    "뉴스": dict(has_date=True, has_time=True, has_source=True, source_label="언론사 도메인"),
    "블로그": dict(has_date=True, has_time=False, has_source=True, source_label="블로거"),
    "카페글": dict(has_date=False, has_time=False, has_source=True, source_label="카페"),
    "웹문서": dict(has_date=False, has_time=False, has_source=False, source_label="도메인"),
    "지식iN": dict(has_date=False, has_time=False, has_source=False, source_label="도메인"),
    "백과사전": dict(has_date=False, has_time=False, has_source=False, source_label="출처 도메인"),
}
TEXT_VERTICALS = tuple(VERTICAL_SPEC)


# --- 캐시되는 무거운 계산 ------------------------------------------------
@st.cache_data(show_spinner=False)
def _features(df: pd.DataFrame, keywords: tuple[str, ...]) -> pd.DataFrame:
    return features.add_text_features(df, list(keywords))


@st.cache_data(show_spinner=False)
def _noun_common(texts: tuple[str, ...], extra_stop: tuple[str, ...]) -> list[tuple[str, int]]:
    return eda.extract_nouns(list(texts), set(extra_stop)).most_common(400)


@st.cache_data(show_spinner=False)
def _cooc_matrix(texts: tuple[str, ...], extra_stop: tuple[str, ...], top_terms: int) -> pd.DataFrame:
    return eda.cooccurrence_matrix(list(texts), set(extra_stop), top_terms)


@st.cache_data(show_spinner=False)
def _tf_by_keyword(df: pd.DataFrame, extra_stop: tuple[str, ...], top_n: int) -> pd.DataFrame:
    return eda.tf_by_group(df, "keyword", set(extra_stop), top_n)


# --- 공통 헬퍼 ----------------------------------------------------------
def _keyword_filter(df: pd.DataFrame, key: str) -> tuple[pd.DataFrame, list[str]]:
    kws = sorted(df["keyword"].dropna().unique().tolist())
    if len(kws) <= 1:
        return df, kws
    picked = st.multiselect("검색어 필터", kws, default=kws, key=f"{key}_kwf")
    picked = picked or kws
    return df[df["keyword"].isin(picked)], picked


def _insight_box(lines: list[str]) -> None:
    if lines:
        st.info("  \n".join(f"- {ln}" for ln in lines))


def _download(df: pd.DataFrame, label: str, fname: str, key: str) -> None:
    st.download_button(
        label, df.to_csv(index=False).encode("utf-8-sig"),
        file_name=fname, mime="text/csv", key=key,
    )


def _grid(n: int = 2):
    return st.columns(n)


_SCOPE = {"name": ""}


def _scope(name: str) -> None:
    _SCOPE["name"] = name


def _pc(fig, *, height: int = 380, legend_bottom: bool = True) -> None:
    """plotly 차트 렌더 + 페이지·제목 기반 고유 key (중복 ID 방지)."""
    title = ""
    try:
        title = fig.layout.title.text or ""
    except Exception:  # noqa: BLE001
        pass
    st.plotly_chart(
        viz.apply_layout(fig, height=height, legend_bottom=legend_bottom),
        width="stretch",
        key=f"{_SCOPE['name']}::{title}",
    )


# ======================================================================
# 텍스트형 공통 템플릿
# ======================================================================
def render_text_vertical(df_all: pd.DataFrame, vertical: str, all_keywords: list[str]) -> None:
    spec = VERTICAL_SPEC[vertical]
    df_v = df_all[df_all["vertical"] == vertical].copy()
    st.header(f"📄 {vertical} 심층 EDA")
    _scope(f"txt-{vertical}")
    if df_v.empty:
        st.warning(f"‘{vertical}’ 수집 결과가 없습니다. 사이드바에서 버티컬을 포함해 다시 수집하세요.")
        return

    df_v, kws = _keyword_filter(df_v, key=f"txt_{vertical}")
    extra_stop = tuple(all_keywords)

    with st.spinner("문서 피처 계산 중…"):
        feat = _features(df_v, tuple(sorted(kws)))
    feat = features.add_length_bins(feat, "title_len")

    multi_kw = feat["keyword"].nunique() > 1
    cmap = viz.color_map(sorted(feat["keyword"].unique()))
    has_date = spec["has_date"] and feat["date"].notna().any()

    # ---- 통계 검정 (인사이트/표에 재사용) ----
    test_rows: list[dict] = []
    test_notes: list[str] = []
    if multi_kw:
        summ, msg = stats_tests.kruskal_by_group(feat, "title_len", "keyword")
        test_rows.append(dict(검정="Kruskal–Wallis", 대상="제목 길이 ~ 검색어",
                              통계량=msg.split(",")[0].replace("H=", "H "), p값=_p(msg), 해석=msg))
        test_notes.append(msg)
        dom_top = feat.assign(dom=_top_bucket(feat["domain"], 6))
        ct, cmsg = stats_tests.chi_square(dom_top, "keyword", "dom")
        test_rows.append(dict(검정="카이제곱", 대상="검색어 × 상위 도메인",
                              통계량=cmsg.split(",")[0], p값=_p(cmsg), 해석=cmsg))
        test_notes.append(cmsg)
    sp = stats_tests.spearman(feat, "title_len", "desc_len")
    test_rows.append(dict(검정="Spearman 상관", 대상="제목 길이 ↔ 본문 길이",
                          통계량=sp.split(",")[0], p값=_p(sp), 해석=sp))
    test_notes.append(sp)

    _insight_box(ins.text_vertical_insights(feat, vertical, has_date, test_notes))

    # ================= 그래프 =================
    st.subheader("📊 그래프")

    g1, g2 = _grid(2)
    with g1:  # 1. 검색어별 문서 수
        cnt = feat.groupby("keyword").size().reset_index(name="문서 수")
        fig = px.bar(cnt, x="keyword", y="문서 수", color="keyword",
                     color_discrete_map=cmap, title="1. 검색어별 문서 수", text_auto=True)
        _pc(fig)
    with g2:  # 2. 길이 분포 (박스)
        lf = feat.melt(id_vars="keyword", value_vars=["title_len", "desc_len"],
                       var_name="구분", value_name="길이")
        lf["구분"] = lf["구분"].map({"title_len": "제목", "desc_len": "본문"})
        fig = px.box(lf, x="구분", y="길이", color="keyword", color_discrete_map=cmap,
                     points="outliers", title="2. 제목·본문 길이 분포(박스)")
        _pc(fig)

    g3, g4 = _grid(2)
    with g3:  # 3. 시계열 or 대체(도메인 트리맵)
        if has_date:
            freq = st.radio("집계 단위", ["일", "주", "월"], horizontal=True,
                            key=f"ts_{vertical}")
            fmap = {"일": "D", "주": "W", "월": "MS"}
            ts = (feat.dropna(subset=["date"])
                  .groupby([pd.Grouper(key="date", freq=fmap[freq]), "keyword"])
                  .size().reset_index(name="문서 수"))
            fig = px.area(ts, x="date", y="문서 수", color="keyword",
                          color_discrete_map=cmap, title="3. 게시량 추이")
        else:
            tm = viz.share_table(feat, "domain", n=20)
            fig = px.treemap(tm, path=["domain"], values="건수",
                             title="3. 상위 도메인 구성(트리맵)")
        _pc(fig)
    with g4:  # 4. 상위 출처/도메인 누적 가로막대
        src_col = "source" if spec["has_source"] else "domain"
        top_src = feat[feat[src_col].astype(str).str.len() > 0]
        order = top_src[src_col].value_counts().head(15).index.tolist()
        sub = top_src[top_src[src_col].isin(order)]
        agg = sub.groupby([src_col, "keyword"]).size().reset_index(name="건수")
        fig = px.bar(agg, x="건수", y=src_col, color="keyword", orientation="h",
                     color_discrete_map=cmap, category_orders={src_col: order[::-1]},
                     title=f"4. 상위 {spec['source_label']} (검색어 누적)")
        _pc(fig, height=440)

    g5, g6 = _grid(2)
    with g5:  # 5. 요일×시간대 히트맵 / 요일 막대 / 도메인×검색어 히트맵
        if has_date and spec["has_time"]:
            hm = (feat.dropna(subset=["date"])
                  .pivot_table(index="pub_dow", columns="pub_hour",
                               values="title", aggfunc="count", fill_value=0)
                  .reindex(["월", "화", "수", "목", "금", "토", "일"]))
            fig = px.imshow(hm, color_continuous_scale=viz.SEQUENTIAL, aspect="auto",
                            labels=dict(color="건수"), title="5. 요일 × 시간대 게시 히트맵")
        elif has_date:
            db = (feat.dropna(subset=["date"]).groupby(["pub_dow", "keyword"])
                  .size().reset_index(name="건수"))
            fig = px.bar(db, x="pub_dow", y="건수", color="keyword", barmode="group",
                         color_discrete_map=cmap,
                         category_orders={"pub_dow": ["월", "화", "수", "목", "금", "토", "일"]},
                         title="5. 요일별 게시량")
        else:
            dk = feat.assign(dom=_top_bucket(feat["domain"], 10))
            hm = pd.crosstab(dk["dom"], dk["keyword"])
            fig = px.imshow(hm, color_continuous_scale=viz.SEQUENTIAL, aspect="auto",
                            labels=dict(color="건수"), title="5. 도메인 × 검색어 히트맵")
        _pc(fig)
    with g6:  # 6. 상위 명사 키워드
        texts = (feat["title"].fillna("") + " " + feat["description"].fillna("")).tolist()
        common = _noun_common(tuple(texts), extra_stop)
        topk = st.slider("상위 키워드 수", 10, 40, 20, key=f"nk_{vertical}")
        kdf = pd.DataFrame(common[:topk], columns=["키워드", "빈도"])
        fig = px.bar(kdf.sort_values("빈도"), x="빈도", y="키워드", orientation="h",
                     title="6. 상위 명사 키워드")
        _pc(fig, height=440)

    # 7. 제목 vs 본문 길이 산점도
    fig = px.scatter(feat, x="title_len", y="desc_len", color="keyword",
                     color_discrete_map=cmap, opacity=0.6, trendline="ols",
                     trendline_scope="overall",
                     labels=dict(title_len="제목 길이(자)", desc_len="본문 길이(자)"),
                     title="7. 제목 길이 vs 본문 길이")
    _pc(fig, height=420)

    # 8. 상위 명사 동시출현 히트맵 (보조)
    with st.expander("명사 동시출현 히트맵"):
        cm = _cooc_matrix(tuple(texts), extra_stop, 15)
        if not cm.empty:
            fig = px.imshow(cm, color_continuous_scale=viz.SEQUENTIAL, aspect="auto",
                            title="상위 15개 명사 동시출현")
            _pc(fig, height=460)

    # ================= 표 =================
    st.subheader("📑 통계표")
    labels = features.NUMERIC_FEATURE_LABELS

    st.markdown("**표 1. 기술통계** (제목·본문 길이/어절/명사 + 왜도·첨도)")
    st.dataframe(stats_tests.describe_plus(feat, features.NUMERIC_FEATURES, labels),
                 width="stretch")

    st.markdown("**표 2. 검색어별 요약 피봇**")
    piv = feat.groupby("keyword").agg(
        문서수=("title", "count"),
        평균_제목길이=("title_len", "mean"),
        평균_본문길이=("desc_len", "mean"),
        평균_제목명사=("title_nouns", "mean"),
        평균_본문명사=("desc_nouns", "mean"),
        고유도메인=("domain", pd.Series.nunique),
        제목_검색어포함률=("kw_in_title", "mean"),
    ).round(2)
    piv["제목_검색어포함률"] = (piv["제목_검색어포함률"] * 100).round(1)
    st.dataframe(piv, width="stretch")

    st.markdown("**표 3. 검색어 × 제목 길이 구간 교차표** + 카이제곱")
    ct = pd.crosstab(feat["keyword"], feat["title_len_bin"])
    st.dataframe(ct, width="stretch")
    if multi_kw:
        _, cmsg = stats_tests.chi_square(feat, "keyword", "title_len_bin")
        st.caption(cmsg)

    st.markdown(f"**표 4. 상위 {spec['source_label']}** (건수·비중·검색어 분해)")
    src_col = "source" if spec["has_source"] else "domain"
    st.dataframe(viz.share_table(feat, src_col, n=20, by="keyword"),
                 width="stretch", hide_index=True)

    st.markdown("**표 5. 상위 명사 키워드 × 검색어 TF + 편중도**")
    st.dataframe(_tf_by_keyword(feat, extra_stop, 25),
                 width="stretch", hide_index=True)

    st.markdown("**표 6. 통계 검정 요약**")
    st.dataframe(stats_tests.test_summary_table(test_rows),
                 width="stretch", hide_index=True)

    st.markdown("**표 7. 검색어 포함률 / 무관 추정 문서**")
    feat_rel = feat.assign(_both_miss=(~feat["kw_in_title"] & ~feat["kw_in_desc"]))
    rel = feat_rel.groupby("keyword").agg(
        문서수=("title", "count"),
        제목포함=("kw_in_title", "sum"),
        본문포함=("kw_in_desc", "sum"),
        둘다_미포함=("_both_miss", "sum"),
    )
    rel["제목포함률(%)"] = (rel["제목포함"] / rel["문서수"] * 100).round(1)
    st.dataframe(rel, width="stretch")

    if has_date:
        st.markdown("**표 7-b. 일자별 게시량 피봇** (검색어 × 날짜)")
        dpiv = feat.dropna(subset=["date"]).pivot_table(
            index="keyword", columns="pub_date", values="title", aggfunc="count", fill_value=0
        )
        st.dataframe(dpiv, width="stretch")

    # 상관행렬 (보조)
    with st.expander("수치 피처 상관행렬 (Spearman)"):
        cm = stats_tests.correlation_matrix(feat, features.NUMERIC_FEATURES, labels)
        fig = px.imshow(cm, text_auto=True, color_continuous_scale="RdBu", zmin=-1, zmax=1,
                        aspect="auto", title="수치 피처 상관행렬")
        _pc(fig, height=420)

    _download(feat, f"{vertical} 피처 포함 CSV", f"naver_{vertical}_features.csv",
              key=f"dl_txt_{vertical}")


# ======================================================================
# 지역
# ======================================================================
def render_local(df_all: pd.DataFrame, all_keywords: list[str]) -> None:
    from src.geo import parse_coord

    st.header("📍 지역 심층 EDA")
    _scope("local")
    df_v = df_all[df_all["vertical"] == "지역"].copy()
    if df_v.empty:
        st.warning("‘지역’ 결과가 없습니다. (지역 검색은 검색어당 최대 5건)")
        return
    df_v, kws = _keyword_filter(df_v, key="local")
    cmap = viz.color_map(sorted(df_v["keyword"].unique()))

    coords = df_v.apply(lambda r: parse_coord(r["mapx"], r["mapy"]), axis=1)
    df_v["lon"] = coords.map(lambda c: c[0] if c else np.nan)
    df_v["lat"] = coords.map(lambda c: c[1] if c else np.nan)
    df_v["시도"] = df_v["address"].fillna("").str.split().str[0]
    df_v["시군구"] = df_v["address"].fillna("").str.split().str[1]
    df_v["대분류업종"] = df_v["category"].fillna("").str.split(">").str[0].str.strip()
    df_v["전화보유"] = df_v["telephone"].astype(str).str.len().gt(0)
    df_v["도로명보유"] = df_v["road_address"].astype(str).str.len().gt(0)

    _insight_box(ins.local_insights(df_v))

    st.subheader("📊 그래프")
    g1, g2 = _grid(2)
    with g1:
        cat = viz.share_table(df_v, "대분류업종", n=15)
        fig = px.bar(cat.sort_values("건수"), x="건수", y="대분류업종", orientation="h",
                     title="1. 업종(대분류) 분포")
        _pc(fig)
    with g2:
        reg = viz.share_table(df_v, "시군구", n=15)
        fig = px.bar(reg.sort_values("건수"), x="건수", y="시군구", orientation="h",
                     title="2. 시군구 분포")
        _pc(fig)

    g3, g4 = _grid(2)
    with g3:
        ct = pd.crosstab(df_v["대분류업종"], df_v["keyword"])
        fig = px.imshow(ct, color_continuous_scale=viz.SEQUENTIAL, aspect="auto",
                        labels=dict(color="건수"), title="3. 업종 × 검색어 히트맵")
        _pc(fig)
    with g4:
        mapped = df_v.dropna(subset=["lat", "lon"])
        if not mapped.empty:
            fig = px.scatter(mapped, x="lon", y="lat", color="keyword",
                             color_discrete_map=cmap, hover_name="title",
                             labels=dict(lon="경도", lat="위도"),
                             title="4. 좌표 산점도(경도·위도)")
            _pc(fig)
        else:
            st.caption("좌표를 해석할 수 있는 항목이 없습니다.")

    g5, g6 = _grid(2)
    with g5:
        av = pd.DataFrame({
            "항목": ["전화번호", "도로명주소", "좌표"],
            "보유율(%)": [
                viz.pct(df_v["전화보유"].sum(), len(df_v)),
                viz.pct(df_v["도로명보유"].sum(), len(df_v)),
                viz.pct(df_v[["lat", "lon"]].notna().all(axis=1).sum(), len(df_v)),
            ],
        })
        fig = px.bar(av, x="항목", y="보유율(%)", title="5. 필드 보유율", text_auto=True)
        _pc(fig)
    with g6:
        kb = df_v.groupby("keyword").size().reset_index(name="건수")
        fig = px.bar(kb, x="keyword", y="건수", color="keyword", color_discrete_map=cmap,
                     title="6. 검색어별 결과 수", text_auto=True)
        _pc(fig)

    st.subheader("🗺️ 지도")
    _render_folium(df_v.dropna(subset=["lat", "lon"]), cmap)

    st.subheader("📑 통계표")
    st.markdown("**표 1. 전체 목록**")
    st.dataframe(df_v[["keyword", "title", "대분류업종", "시군구", "address",
                       "road_address", "telephone", "link"]],
                 width="stretch", hide_index=True)
    st.markdown("**표 2. 업종별 집계**")
    st.dataframe(viz.share_table(df_v, "대분류업종", n=30), width="stretch", hide_index=True)
    st.markdown("**표 3. 시군구별 집계**")
    st.dataframe(viz.share_table(df_v, "시군구", n=30), width="stretch", hide_index=True)
    st.markdown("**표 4. 검색어 × 업종 교차표**")
    st.dataframe(pd.crosstab(df_v["keyword"], df_v["대분류업종"]), width="stretch")
    st.markdown("**표 5. 좌표 기술통계**")
    st.dataframe(stats_tests.describe_plus(df_v, ["lat", "lon"],
                 {"lat": "위도", "lon": "경도"}), width="stretch")
    st.markdown("**표 6. 필드 결측률**")
    miss = pd.DataFrame({
        "필드": ["업종", "전화번호", "도로명주소", "좌표"],
        "결측(%)": [
            viz.pct((df_v["category"].astype(str).str.len() == 0).sum(), len(df_v)),
            viz.pct((~df_v["전화보유"]).sum(), len(df_v)),
            viz.pct((~df_v["도로명보유"]).sum(), len(df_v)),
            viz.pct(df_v[["lat", "lon"]].isna().any(axis=1).sum(), len(df_v)),
        ],
    })
    st.dataframe(miss, width="stretch", hide_index=True)

    _download(df_v, "지역 데이터 CSV", "naver_지역_features.csv", key="dl_local")


def _render_folium(mapped: pd.DataFrame, cmap: dict) -> None:
    if mapped.empty:
        st.caption("표시할 좌표가 없습니다.")
        return
    try:
        import folium
        from streamlit_folium import st_folium

        fmap = folium.Map(location=[mapped["lat"].mean(), mapped["lon"].mean()], zoom_start=11)
        for _, r in mapped.iterrows():
            folium.CircleMarker(
                [r["lat"], r["lon"]], radius=6, color=cmap.get(r["keyword"], "#333"),
                fill=True, fill_opacity=0.8,
                popup=f"{r['title']} ({r['keyword']})", tooltip=r["title"],
            ).add_to(fmap)
        st_folium(fmap, use_container_width=True, height=460)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"지도 렌더링 건너뜀: {exc}")
        st.map(mapped.rename(columns={"lat": "latitude", "lon": "longitude"})
               [["latitude", "longitude"]])


# ======================================================================
# 이미지
# ======================================================================
def render_image(df_all: pd.DataFrame, all_keywords: list[str]) -> None:
    st.header("🖼️ 이미지 심층 EDA")
    _scope("image")
    df_v = df_all[df_all["vertical"] == "이미지"].copy()
    if df_v.empty:
        st.warning("‘이미지’ 결과가 없습니다.")
        return
    df_v, kws = _keyword_filter(df_v, key="image")
    cmap = viz.color_map(sorted(df_v["keyword"].unique()))

    df_v["img_width"] = pd.to_numeric(df_v["img_width"], errors="coerce")
    df_v["img_height"] = pd.to_numeric(df_v["img_height"], errors="coerce")
    valid = df_v.dropna(subset=["img_width", "img_height"]).copy()
    valid = valid[(valid["img_width"] > 0) & (valid["img_height"] > 0)]
    valid["종횡비"] = (valid["img_width"] / valid["img_height"]).round(2)
    valid["메가픽셀"] = (valid["img_width"] * valid["img_height"] / 1e6).round(2)
    valid["방향"] = np.select(
        [valid["종횡비"] > 1.15, valid["종횡비"] < 0.87],
        ["가로형", "세로형"], default="정사각",
    )
    valid["해상도구간"] = pd.cut(
        valid["메가픽셀"], [0, 0.1, 0.5, 2, 8, np.inf],
        labels=["≤0.1MP", "0.1–0.5MP", "0.5–2MP", "2–8MP", ">8MP"],
    )

    _insight_box(ins.image_insights(df_v))
    if valid.empty:
        st.warning("해상도(가로·세로) 정보가 있는 이미지가 없어 그래프 일부를 생략합니다.")

    st.subheader("📊 그래프")
    if not valid.empty:
        g1, g2 = _grid(2)
        with g1:
            fig = px.scatter(valid, x="img_width", y="img_height", color="keyword",
                             color_discrete_map=cmap, opacity=0.6,
                             labels=dict(img_width="너비(px)", img_height="높이(px)"),
                             title="1. 이미지 해상도 분포")
            _pc(fig)
        with g2:
            fig = px.histogram(valid, x="종횡비", color="keyword", color_discrete_map=cmap,
                               nbins=40, title="2. 종횡비 분포")
            _pc(fig)

        g3, g4 = _grid(2)
        with g3:
            ob = valid.groupby(["방향", "keyword"]).size().reset_index(name="건수")
            fig = px.bar(ob, x="방향", y="건수", color="keyword", barmode="group",
                         color_discrete_map=cmap, title="3. 방향 분류별 이미지 수")
            _pc(fig)
        with g4:
            fig = px.box(valid, x="keyword", y="메가픽셀", color="keyword",
                         color_discrete_map=cmap, points="outliers",
                         title="4. 검색어별 메가픽셀 분포")
            _pc(fig)

        g5, g6 = _grid(2)
        with g5:
            ct = pd.crosstab(valid["해상도구간"], valid["keyword"])
            fig = px.imshow(ct, color_continuous_scale=viz.SEQUENTIAL, aspect="auto",
                            labels=dict(color="건수"), title="5. 해상도 구간 × 검색어")
            _pc(fig)
        with g6:
            dom = viz.share_table(df_v, "domain", n=15)
            fig = px.bar(dom.sort_values("건수"), x="건수", y="domain", orientation="h",
                         title="6. 상위 출처 도메인")
            _pc(fig)
    else:
        dom = viz.share_table(df_v, "domain", n=15)
        fig = px.bar(dom.sort_values("건수"), x="건수", y="domain", orientation="h",
                     title="상위 출처 도메인")
        _pc(fig)

    st.subheader("📑 통계표")
    st.markdown("**표 1. 해상도 기술통계**")
    st.dataframe(stats_tests.describe_plus(
        valid, ["img_width", "img_height", "메가픽셀", "종횡비"],
        {"img_width": "너비(px)", "img_height": "높이(px)"}), width="stretch")
    st.markdown("**표 2. 검색어별 해상도 피봇**")
    if not valid.empty:
        st.dataframe(valid.groupby("keyword").agg(
            이미지수=("link", "count"),
            평균너비=("img_width", "mean"),
            평균높이=("img_height", "mean"),
            평균메가픽셀=("메가픽셀", "mean"),
            평균종횡비=("종횡비", "mean"),
        ).round(2), width="stretch")
    st.markdown("**표 3. 검색어 × 방향 교차표** + 카이제곱")
    if not valid.empty:
        ct = pd.crosstab(valid["keyword"], valid["방향"])
        st.dataframe(ct, width="stretch")
        if valid["keyword"].nunique() > 1:
            _, msg = stats_tests.chi_square(valid, "keyword", "방향")
            st.caption(msg)
    st.markdown("**표 4. 상위 출처 도메인**")
    st.dataframe(viz.share_table(df_v, "domain", n=25, by="keyword"),
                 width="stretch", hide_index=True)
    st.markdown("**표 5. 종횡비 구간 분포**")
    if not valid.empty:
        ar_bin = pd.cut(valid["종횡비"], [0, 0.75, 0.95, 1.05, 1.34, 1.78, np.inf],
                        labels=["세로<3:4", "3:4~1:1", "≈정사각", "1:1~4:3", "4:3~16:9", ">16:9"])
        st.dataframe(ar_bin.value_counts().sort_index().rename_axis("구간")
                     .reset_index(name="건수"), width="stretch", hide_index=True)

    st.subheader("🖼️ 썸네일")
    n_show = st.slider("표시 개수", 5, min(50, len(df_v)), min(15, len(df_v)), key="img_thumb_n")
    cols = st.columns(5)
    for i, (_, row) in enumerate(df_v.head(n_show).iterrows()):
        with cols[i % 5]:
            if row["thumbnail"]:
                st.image(row["thumbnail"], width="stretch")
            st.caption(f"[{row['domain'] or '출처'}]({row['link']})")

    _download(df_v, "이미지 데이터 CSV", "naver_이미지_features.csv", key="dl_image")


# ======================================================================
# 전역 교차분석
# ======================================================================
def render_cross_vertical(df_all: pd.DataFrame, all_keywords: list[str]) -> None:
    st.header("🔀 버티컬 교차분석")
    _scope("cross")
    if df_all.empty:
        st.info("데이터가 없습니다.")
        return
    extra_stop = tuple(all_keywords)
    cmap = viz.color_map(sorted(df_all["keyword"].unique()))
    vmap = viz.color_map(sorted(df_all["vertical"].unique()))

    _insight_box(ins.cross_vertical_insights(df_all))

    st.subheader("📊 그래프")
    g1, g2 = _grid(2)
    with g1:
        cnt = df_all.groupby(["vertical", "keyword"]).size().reset_index(name="문서 수")
        fig = px.bar(cnt, x="vertical", y="문서 수", color="keyword", barmode="group",
                     color_discrete_map=cmap, title="1. 검색어 × 버티컬 문서 수")
        _pc(fig)
    with g2:
        comp = df_all.groupby(["keyword", "vertical"]).size().reset_index(name="건수")
        fig = px.bar(comp, x="keyword", y="건수", color="vertical", barmode="stack",
                     color_discrete_map=vmap, title="2. 검색어별 버티컬 구성")
        fig.update_layout(barnorm="percent")
        _pc(fig)

    g3, g4 = _grid(2)
    with g3:
        dated = df_all.dropna(subset=["date"])
        if not dated.empty:
            ts = (dated.groupby([pd.Grouper(key="date", freq="D"), "vertical"])
                  .size().reset_index(name="문서 수"))
            fig = px.line(ts, x="date", y="문서 수", color="vertical",
                          color_discrete_map=vmap, title="3. 버티컬별 게시량 추이(뉴스·블로그)")
            _pc(fig)
        else:
            st.caption("3. 날짜 정보가 있는 문서가 없습니다.")
    with g4:
        with st.spinner("버티컬 간 키워드 유사도 계산 중…"):
            sets = eda.keyword_noun_sets(df_all, "vertical", set(extra_stop))
            jm = eda.jaccard_matrix(sets)
        fig = px.imshow(jm, text_auto=True, color_continuous_scale=viz.SEQUENTIAL,
                        aspect="auto", title="4. 버티컬 쌍 키워드 자카드 유사도")
        _pc(fig, height=420)

    texts = (df_all["title"].fillna("") + " " + df_all["description"].fillna("")).tolist()
    common = _noun_common(tuple(texts), extra_stop)
    kdf = pd.DataFrame(common[:25], columns=["키워드", "빈도"])
    fig = px.bar(kdf.sort_values("빈도"), x="빈도", y="키워드", orientation="h",
                 title="5. 전역 상위 명사 키워드")
    _pc(fig, height=460)

    with st.expander("전역 워드클라우드"):
        from collections import Counter
        fig_wc = eda.make_wordcloud_figure(Counter(dict(common)))
        if fig_wc:
            st.pyplot(fig_wc)

    st.subheader("📑 통계표")
    st.markdown("**표 1. 검색어 × 버티컬 문서 수 피봇**")
    st.dataframe(pd.crosstab(df_all["keyword"], df_all["vertical"], margins=True,
                             margins_name="합계"), width="stretch")
    st.markdown("**표 2. 버티컬별 요약 통계**")
    vs = df_all.groupby("vertical").agg(
        문서수=("title", "count"),
        검색어수=("keyword", pd.Series.nunique),
        고유도메인=("domain", pd.Series.nunique),
        평균제목길이=("title", lambda s: round(s.str.len().mean(), 1)),
        날짜보유율=("date", lambda s: round(s.notna().mean() * 100, 1)),
    )
    st.dataframe(vs, width="stretch")
    st.markdown("**표 3. 버티컬 쌍 자카드 유사도**")
    st.dataframe(jm, width="stretch")
    st.markdown("**표 4. 전역 상위 명사 × 버티컬 출현**")
    st.dataframe(eda.tf_by_group(df_all, "vertical", set(extra_stop), 25),
                 width="stretch", hide_index=True)
    st.markdown("**표 5. 수집 커버리지**")
    cov = df_all.groupby(["keyword", "vertical"]).size().reset_index(name="건수")
    st.dataframe(cov.pivot(index="keyword", columns="vertical", values="건수").fillna(0),
                 width="stretch")


# --- 작은 유틸 ---------------------------------------------------------
def _top_bucket(series: pd.Series, n: int) -> pd.Series:
    top = series.value_counts().head(n).index
    return series.where(series.isin(top), "기타")


def _p(msg: str) -> str:
    import re
    m = re.search(r"p=([0-9.]+)", msg)
    return m.group(1) if m else ""

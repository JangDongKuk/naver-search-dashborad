"""네이버 검색 API 마켓 인사이트 EDA 대시보드.

실행:  uv run streamlit run src/app.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (  # noqa: E402
    DATALAB_AGES,
    DATALAB_DEVICES,
    DATALAB_GENDERS,
    DATALAB_MIN_DATE,
    DEFAULT_COLLECT_SIZE,
    MAX_KEYWORDS_SEARCH,
    MAX_KEYWORDS_TREND,
    SEARCH_VERTICALS,
    START_MAX,
)
from src import viz  # noqa: E402,F401  (import 시 plotly 기본 팔레트 적용)
from src import eda, export, vertical_eda  # noqa: E402
from src.collect import CollectResult, collect_search, collect_trend  # noqa: E402
from src.credentials import load_credentials  # noqa: E402
from src.naver_client import NaverAPIError, NaverClient  # noqa: E402

st.set_page_config(page_title="네이버 마켓 인사이트 EDA", page_icon="📊", layout="wide")

PRESETS = {
    "최근 7일": 7,
    "최근 30일": 30,
    "최근 90일": 90,
    "최근 1년": 365,
    "직접 선택": None,
}
TEXT_VERTICALS = set(vertical_eda.VERTICAL_SPEC)


# --------------------------------------------------------------------------
def render_setup_guide(creds) -> None:
    st.title("📊 네이버 마켓 인사이트 EDA 대시보드")
    from config.settings import NAVER_API_PLATFORM  # noqa: PLC0415

    st.error("네이버 API 자격증명이 없거나 인증에 실패했습니다. 아래 절차대로 `.env` 를 확인하세요.")
    st.markdown(
        f"""
### 설정 방법 (현재 플랫폼: `{NAVER_API_PLATFORM}`)

1. **애플리케이션 등록**
   - `apihub` — [NAVER Cloud Platform › API Hub](https://api.ncloud-docs.com/docs/naver-api-hub-overview)
   - `developers` — [네이버 개발자센터 › 앱 등록](https://developers.naver.com/apps/#/register)
2. **이용 API 추가** — *검색* 8종 + *검색어 트렌드(Search Trend / 데이터랩)* 를 **모두** 신청
3. **키 복사** — 발급된 **Client ID** / **Client Secret**
4. **`.env` 작성** — 프로젝트 루트의 `.env` 에 입력 후 이 페이지 새로고침

```
NAVER_API_PLATFORM={NAVER_API_PLATFORM}
NAVER_CLIENT_ID=발급받은_client_id
NAVER_CLIENT_SECRET=발급받은_client_secret
```

`.env` 파일 위치: `{Path('.env').resolve()}`
"""
    )
    cur_id = "설정됨" if creds.client_id else "비어 있음"
    cur_sec = "설정됨" if creds.client_secret else "비어 있음"
    st.info(f"현재 상태 — CLIENT_ID: **{cur_id}**, CLIENT_SECRET: **{cur_sec}**")
    if st.button("🔄 다시 확인"):
        st.rerun()


# --------------------------------------------------------------------------
def sidebar_controls() -> dict:
    st.sidebar.header("① 검색어 & 기간")
    raw_kw = st.sidebar.text_input(
        "검색어 (콤마로 구분)", value="아이폰, 갤럭시",
        help=f"검색 최대 {MAX_KEYWORDS_SEARCH}개, 트렌드 비교는 앞 {MAX_KEYWORDS_TREND}개",
    )
    keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]

    preset = st.sidebar.selectbox("기간 프리셋", list(PRESETS.keys()), index=1)
    today = date.today()
    min_d = datetime.strptime(DATALAB_MIN_DATE, "%Y-%m-%d").date()
    if PRESETS[preset] is None:
        d_range = st.sidebar.date_input(
            "기간 직접 선택", value=(today - timedelta(days=30), today),
            min_value=min_d, max_value=today,
        )
        if isinstance(d_range, tuple) and len(d_range) == 2:
            start_d, end_d = d_range
        else:
            start_d, end_d = today - timedelta(days=30), today
    else:
        start_d, end_d = today - timedelta(days=PRESETS[preset]), today
        st.sidebar.caption(f"기간: {start_d} ~ {end_d}")

    st.sidebar.header("② 수집 옵션")
    size = st.sidebar.slider(
        "버티컬·검색어당 최대 수집 건수", 100, START_MAX, DEFAULT_COLLECT_SIZE, step=100,
        help="지역은 API 제한으로 항상 최대 5건",
    )
    verticals = st.sidebar.multiselect(
        "검색 버티컬", list(SEARCH_VERTICALS.keys()), default=list(SEARCH_VERTICALS.keys())
    )
    st.sidebar.caption(
        "기간 필터는 응답에 날짜가 있는 **뉴스·블로그**에만 적용됩니다. "
        "나머지는 최신/정확도순 상위 N건."
    )
    force = st.sidebar.checkbox("캐시 무시하고 새로 수집", value=False)

    st.sidebar.header("③ 검색어 트렌드(데이터랩)")
    span_days = (end_d - start_d).days
    default_unit = "date" if span_days <= 92 else "month"
    unit_label = st.sidebar.radio(
        "집계 단위", ["일", "주", "월"],
        index=["date", "week", "month"].index(default_unit), horizontal=True,
    )
    time_unit = {"일": "date", "주": "week", "월": "month"}[unit_label]
    device = DATALAB_DEVICES[st.sidebar.selectbox("기기", list(DATALAB_DEVICES))]
    gender = DATALAB_GENDERS[st.sidebar.selectbox("성별", list(DATALAB_GENDERS))]
    age_labels = st.sidebar.multiselect("연령대", list(DATALAB_AGES))
    ages = [DATALAB_AGES[a] for a in age_labels]

    run = st.sidebar.button("🚀 데이터 수집 실행", type="primary", width="stretch")

    return dict(
        keywords=keywords, start_d=start_d, end_d=end_d, size=size, verticals=verticals,
        force=force, time_unit=time_unit, device=device, gender=gender, ages=ages, run=run,
    )


# --------------------------------------------------------------------------
def do_collect(client: NaverClient, cfg: dict) -> None:
    kws = cfg["keywords"][:MAX_KEYWORDS_SEARCH]
    if len(cfg["keywords"]) > MAX_KEYWORDS_SEARCH:
        st.warning(f"검색어가 {MAX_KEYWORDS_SEARCH}개를 초과하여 앞 {MAX_KEYWORDS_SEARCH}개만 사용합니다.")

    bar = st.progress(0.0, text="검색 API 수집 중…")

    def cb(done, total, status):
        bar.progress(done / total, text=f"[{done}/{total}] {status.keyword} · {status.vertical}")

    try:
        result = collect_search(
            client, kws, cfg["verticals"], cfg["size"], cfg["start_d"], cfg["end_d"],
            use_cache=not cfg["force"], progress_cb=cb,
        )
    except NaverAPIError as exc:
        bar.empty()
        st.error(f"수집 실패: {exc}")
        return
    bar.empty()
    st.session_state["search_result"] = result
    st.session_state["search_cfg"] = cfg

    trend_kws = kws[:MAX_KEYWORDS_TREND]
    try:
        with st.spinner("검색어 트렌드 수집 중…"):
            tdf = collect_trend(
                client, trend_kws, cfg["start_d"], cfg["end_d"], cfg["time_unit"],
                cfg["device"], cfg["gender"], cfg["ages"],
            )
        st.session_state["trend_df"] = tdf
        st.session_state["trend_err"] = ""
    except NaverAPIError as exc:
        st.session_state["trend_df"] = pd.DataFrame()
        st.session_state["trend_err"] = str(exc)


# --------------------------------------------------------------------------
def tab_overview(result: CollectResult) -> None:
    df = result.df
    if result.from_cache:
        st.info("💾 캐시된 결과입니다. 사이드바 ‘캐시 무시하고 새로 수집’으로 갱신하세요.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 수집 문서", f"{len(df):,}")
    c2.metric("검색어 수", df["keyword"].nunique() if not df.empty else 0)
    c3.metric("버티컬 수", df["vertical"].nunique() if not df.empty else 0)
    c4.metric("날짜 보유 문서", f"{df['date'].notna().sum() if not df.empty else 0:,}")

    st.subheader("수집 상태")
    srows = [
        {
            "검색어": s.keyword, "버티컬": s.vertical,
            "상태": "✅ 성공" if s.ok else "❌ 실패",
            "수집": s.count, "API 총건수": s.total_available,
            "기간 미충족": "⚠️" if s.truncated_by_period else "",
            "메시지": s.message,
        }
        for s in sorted(result.statuses, key=lambda x: (x.keyword, x.vertical))
    ]
    st.dataframe(pd.DataFrame(srows), width="stretch", hide_index=True)
    if any(s.truncated_by_period for s in result.statuses):
        st.warning(
            f"일부 검색어는 API 한도(최대 {START_MAX}건)로 선택 기간을 모두 덮지 못했습니다. "
            "기간을 좁히면 완전한 수집이 가능합니다."
        )
    if any(not s.ok for s in result.statuses):
        st.error("실패한 버티컬이 있습니다. 상태표의 메시지를 확인하고 사이드바에서 재수집하세요.")

    if not df.empty:
        st.subheader("검색어 × 버티컬 문서 수")
        sc = eda.summary_counts(df)
        st.dataframe(
            sc.pivot_table(index="keyword", columns="vertical", values="count", fill_value=0),
            width="stretch",
        )
        fig = px.bar(sc, x="vertical", y="count", color="keyword", barmode="group",
                     title="버티컬별 수집 문서 수")
        st.plotly_chart(viz.apply_layout(fig), width="stretch", key="ov_bar")


def tab_trend() -> None:
    err = st.session_state.get("trend_err", "")
    tdf = st.session_state.get("trend_df", pd.DataFrame())
    st.caption("데이터랩 검색어 트렌드 — 값은 기간 내 최대 검색량을 100으로 한 상대 비율입니다.")
    if err:
        st.error(f"검색어 트렌드 조회 실패: {err}")
        return
    if tdf is None or tdf.empty:
        st.info("트렌드 데이터가 없습니다.")
        return
    cmap = viz.color_map(sorted(tdf["keyword"].unique()))
    fig = px.line(tdf, x="period", y="ratio", color="keyword", markers=True,
                  color_discrete_map=cmap, title="검색어 트렌드 비교")
    st.plotly_chart(viz.apply_layout(fig, height=420), width="stretch", key="tr_main")

    c1, c2 = st.columns(2)
    with c1:
        roll = tdf.sort_values("period").copy()
        roll["7일 이동평균"] = roll.groupby("keyword")["ratio"].transform(
            lambda s: s.rolling(7, min_periods=1).mean()
        )
        fig = px.line(roll, x="period", y="7일 이동평균", color="keyword",
                      color_discrete_map=cmap, title="이동평균(평활)")
        st.plotly_chart(viz.apply_layout(fig), width="stretch", key="tr_roll")
    with c2:
        desc = tdf.groupby("keyword")["ratio"].describe().round(1)
        st.markdown("**트렌드 기술통계**")
        st.dataframe(desc, width="stretch")

    pivot = tdf.pivot_table(index="period", columns="keyword", values="ratio")
    st.markdown("**기간 × 검색어 피봇**")
    st.dataframe(pivot, width="stretch")
    st.download_button("트렌드 CSV", pivot.to_csv().encode("utf-8-sig"),
                       file_name="naver_search_trend.csv", mime="text/csv")


def tab_raw(result: CollectResult, cfg: dict) -> None:
    df = result.df
    if df.empty:
        st.info("데이터가 없습니다.")
        return

    st.subheader("엑셀 통합 내보내기")
    if st.button("📥 xlsx 생성 (원본 + 기술통계 + 피봇 + 트렌드)"):
        with st.spinner("엑셀 생성 중…"):
            xlsx = export.build_excel(
                df, st.session_state.get("trend_df", pd.DataFrame()), cfg, result.statuses
            )
        st.download_button(
            "다운로드: naver_insight.xlsx", xlsx,
            file_name=f"naver_insight_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.divider()
    st.download_button(
        "전체 데이터 CSV", df.to_csv(index=False).encode("utf-8-sig"),
        file_name="naver_search_all.csv", mime="text/csv",
    )
    for v in sorted(df["vertical"].unique()):
        sub = df[df["vertical"] == v]
        with st.expander(f"{v} · {len(sub):,}건"):
            st.dataframe(sub, width="stretch", hide_index=True)
            st.download_button(
                f"{v} CSV", sub.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"naver_search_{v}.csv", mime="text/csv", key=f"dl_{v}",
            )


# --------------------------------------------------------------------------
_VERTICAL_ICON = {
    "뉴스": "📰", "블로그": "✍️", "웹문서": "🌐", "이미지": "🖼️",
    "지식iN": "💬", "지역": "📍", "카페글": "☕", "백과사전": "📚",
}


def render_vertical_tab(vertical: str, result: CollectResult, keywords: list[str]) -> None:
    if vertical == "지역":
        vertical_eda.render_local(result.df, keywords)
    elif vertical == "이미지":
        vertical_eda.render_image(result.df, keywords)
    else:
        vertical_eda.render_text_vertical(result.df, vertical, keywords)


def main() -> None:
    creds = load_credentials()
    if not creds.is_complete:
        render_setup_guide(creds)
        return

    st.title("📊 네이버 마켓 인사이트 EDA 대시보드")
    cfg = sidebar_controls()

    if cfg["run"]:
        if not cfg["keywords"]:
            st.error("검색어를 1개 이상 입력하세요.")
        elif not cfg["verticals"]:
            st.error("버티컬을 1개 이상 선택하세요.")
        else:
            try:
                do_collect(NaverClient(creds), cfg)
            except NaverAPIError as exc:
                st.error(str(exc))
                render_setup_guide(creds)
                return

    result: CollectResult | None = st.session_state.get("search_result")
    if result is None:
        st.info("좌측에서 검색어·기간·옵션을 설정하고 **‘데이터 수집 실행’** 을 눌러주세요.")
        return

    used_cfg = st.session_state.get("search_cfg", cfg)
    keywords = used_cfg.get("keywords", [])
    present = [v for v in SEARCH_VERTICALS if (result.df["vertical"] == v).any()]

    global_labels = ["📋 개요", "🔀 교차분석", "📈 검색어 트렌드", "💾 원본·엑셀"]
    vert_labels = [f"{_VERTICAL_ICON.get(v, '📄')} {v}" for v in present]
    tabs = st.tabs(global_labels + vert_labels)

    with tabs[0]:
        tab_overview(result)
    with tabs[1]:
        vertical_eda.render_cross_vertical(result.df, keywords)
    with tabs[2]:
        tab_trend()
    with tabs[3]:
        tab_raw(result, used_cfg)
    for i, v in enumerate(present):
        with tabs[4 + i]:
            render_vertical_tab(v, result, keywords)


if __name__ == "__main__":
    main()

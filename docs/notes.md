# 설계 메모 / 네이버 API 제약 정리

## 참고 문서
- NAVER API Hub 개요: https://api.ncloud-docs.com/docs/naver-api-hub-overview
- 검색 API (개발자센터): https://developers.naver.com/docs/serviceapi/search/blog/blog.md
- 데이터랩 검색어 트렌드: https://developers.naver.com/docs/serviceapi/datalab/search/search.md

## 이 프로젝트가 쓰는 엔드포인트

플랫폼은 `.env` 의 `NAVER_API_PLATFORM` 으로 전환 (`config/settings.py` 의 `_PLATFORMS`).

### apihub (기본, NAVER Cloud Platform / API Hub)
| 구분 | 메서드 | URL |
|---|---|---|
| 검색 8종 | GET | `https://naverapihub.apigw.ntruss.com/search/v1/{news,blog,webkr,image,kin,local,cafearticle,encyc}` + `format=json` |
| 검색어 트렌드 | POST | `https://naverapihub.apigw.ntruss.com/search-trend/v1/search` |

인증 헤더: `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY`

### developers (레거시, 2026-07-31 검색 API 종료 예정)
| 구분 | 메서드 | URL |
|---|---|---|
| 검색 8종 | GET | `https://openapi.naver.com/v1/search/{news.json,blog.json,...}` |
| 검색어 트렌드 | POST | `https://openapi.naver.com/v1/datalab/search` |

인증 헤더: `X-Naver-Client-Id`, `X-Naver-Client-Secret`

> 두 플랫폼 모두 요청 파라미터(`query/display/start/sort`)와 응답 스키마
> (`total`, `items[]`, `bloggername`, `postdate`, `pubDate`, `mapx/mapy` 등)는 동일하다.
> 실측 확인: 검색·트렌드 모두 apihub 에서 정상 동작.

## 핵심 제약 (설계에 반영됨)
1. **검색 API 에는 기간(startDate/endDate) 파라미터가 없다.**
   - `query`, `display`(≤100), `start`(≤1000), `sort`(`sim`|`date`) 만 존재.
   - 따라서 `start+display-1 ≤ 1000`, 검색어·버티컬당 최대 1,000건.
2. **응답에 날짜가 있는 버티컬은 뉴스(`pubDate`), 블로그(`postdate`) 뿐.**
   - 이 둘만 `sort=date` 로 당겨와 클라이언트에서 기간 필터. 기간 시작일 도달 시 조기 중단.
   - 1,000건으로 기간을 못 덮으면 "기간 미충족" 경고.
   - 나머지 6종(웹문서·이미지·지식iN·지역·카페글·백과사전)은 기간 무시, 상위 N건.
3. **지역 검색은 검색어당 최대 5건**, `sort` 는 `random`/`comparison` 이라 날짜순 없음.
4. **검색어 트렌드**만 기간이 실제 의미를 가짐.
   - `keywordGroups` 최대 5개 → 콤마 검색어 앞 5개를 각각 그룹으로(경쟁 비교).
   - 값은 기간 내 최댓값=100 상대 비율. `timeUnit`: `date`/`week`/`month`.
   - 최소 시작일 2016-01-01.
5. 일일 호출 한도 초과 시 HTTP 429. → 1회 지수 백오프 후 실패 처리, 다른 버티컬은 계속.

## 수집 전략
- 검색어 × 버티컬 을 `ThreadPoolExecutor(max_workers=4)` 로 병렬, 페이지네이션은 순차, 호출 간 0.1s.
- 파라미터(검색어·버티컬·건수·기간) SHA1 해시로 `data/cache/search_<hash>.parquet` 캐시.
  사이드바 "캐시 무시하고 새로 수집" 으로 강제 갱신.

## EDA 탭 구조
전역: 개요 / 버티컬 교차분석 / 검색어 트렌드 / 원본·엑셀
검색 항목별(수집된 것만): 뉴스·블로그·카페글·웹문서·지식iN·백과사전(공통 텍스트 템플릿) · 지역 · 이미지

- 한국어 명사 추출: `kiwipiepy` (NNG/NNP, 2글자 이상, `config/stopwords_ko.txt` 불용어 + 검색어 제외).
- 워드클라우드 폰트: Windows `malgun.ttf` 우선 자동 탐색.
- 색상: 색각이상 대응 팔레트(범주형 Carto Safe, 순차형 Viridis), 엔티티→색 고정(`viz.color_map`).
- 무거운 계산(형태소 분석·동시출현·피처)은 `st.cache_data` 로 캐시.
- `st.plotly_chart` 는 페이지+제목 기반 key 로 중복 ID 방지(`vertical_eda._pc`).

## 문서 단위 수치 피처 사전 (`src/features.py`)
| 피처 | 정의 |
|---|---|
| `title_len` / `desc_len` | 제목 / 본문(요약) 문자 수 (HTML 태그 제거 후, 공백 포함) |
| `title_words` / `desc_words` | 공백 분리 어절 수 |
| `title_nouns` / `desc_nouns` | kiwipiepy 기준 명사(NNG·NNP) 수 |
| `kw_in_title` / `kw_in_desc` | 해당 문서의 검색어가 제목 / 본문에 포함되는가 (bool) |
| `kw_pos_title` | 제목에서 검색어 첫 등장 문자 인덱스 (없으면 -1) |
| `is_naver_domain` | 링크 도메인이 `*.naver.com` 인가 |
| `pub_date` / `pub_dow` / `pub_week` / `pub_hour` / `pub_month` | 발행일 파생값 (뉴스·블로그만) |
| `title_len_bin` | 제목 길이 3분위 (단문/중문/장문, `pd.qcut`) |

## 통계 계산 (`src/stats_tests.py`)
- `describe_plus` — n·평균·표준편차·사분위·최대/최소 + 왜도·첨도 + 결측
- `chi_square` — 두 범주의 독립성 카이제곱 + Cramér's V (연관 강도)
- `kruskal_by_group` — 그룹 간 분포 차이(비모수 ANOVA), `mann_whitney` 는 2집단
- `spearman` / `correlation_matrix` — 순위상관
- 모든 결과에 `p<0.05` 기준 "유의함/유의하지 않음" 해석 문구 부착
- 교차분석: `eda.jaccard_matrix` 로 버티컬 쌍 키워드 집합 유사도

## 의존성 메모
- `scipy` — 추론통계, `statsmodels` — plotly 산점도 OLS 추세선, `openpyxl` — xlsx 내보내기

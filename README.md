# 네이버 마켓 인사이트 EDA 대시보드

네이버 **검색 API 8종**(뉴스·블로그·웹문서·이미지·지식iN·지역·카페글·백과사전)과
**데이터랩 검색어 트렌드**를 콤마로 구분한 검색어 단위로 수집해, 검색 항목별 심층 EDA
(그래프·통계표·추론통계)를 보여주는 Streamlit 대시보드입니다.
공식 문서: <https://api.ncloud-docs.com/docs/naver-api-hub-overview>

## 폴더 구조 (파일 종류별)

```
config/       설정 · 자격증명 예시 · 불용어 사전
  ├─ settings.py        플랫폼/엔드포인트/한도/시각화 상수
  ├─ .env.example       자격증명 템플릿
  └─ stopwords_ko.txt   한국어 불용어
src/          파이썬 소스
  ├─ credentials.py     .env 로더
  ├─ naver_client.py    검색/트렌드 API 저수준 클라이언트
  ├─ collect.py         수집 오케스트레이션 · 페이지네이션 · parquet 캐시
  ├─ features.py        문서 단위 수치 피처 엔지니어링
  ├─ eda.py             집계 · 형태소 분석 · 동시출현 · 자카드 · 워드클라우드
  ├─ stats_tests.py     기술통계 + 추론통계(scipy): 카이제곱·Kruskal–Wallis·Spearman
  ├─ viz.py             색맹 안전 팔레트 · plotly 공통 레이아웃
  ├─ insights.py        규칙 기반 인사이트 요약 (LLM 미사용)
  ├─ vertical_eda.py    버티컬별 심층 EDA 렌더러 (텍스트형 공통 + 지역 + 이미지 + 교차)
  ├─ export.py          엑셀(xlsx) 통합 내보내기
  ├─ geo.py             지역 좌표 변환
  └─ app.py             Streamlit 진입점
data/         수집 결과 parquet 캐시 (data/cache/)
notebooks/    탐색용 노트북
docs/         설계 메모 · API 제약 정리 · 지표 사전 (docs/notes.md)
.streamlit/   서버 설정 (포트 8501)
```

## 설치 (uv)

```powershell
uv sync
```

## 배포용 requirements.txt

의존성의 단일 진실 공급원은 `pyproject.toml` + `uv.lock` 이지만, `requirements.txt`(pip 고정 버전
목록)도 함께 제공합니다 — Streamlit Community Cloud 등 uv 를 모르는 배포 환경에서 사용합니다.
`uv.lock` 을 바꾼 뒤에는 아래로 재생성하세요(직접 수정하지 마세요):

```powershell
uv export --no-hashes --no-annotate --format requirements.txt -o requirements.txt
```

## 네이버 API 키 설정

기본값은 **NAVER Cloud Platform / API Hub** (`NAVER_API_PLATFORM=apihub`).
기존 개발자센터 키를 쓰려면 `developers` 로 바꾸면 됩니다.

1. [NAVER API Hub](https://api.ncloud-docs.com/docs/naver-api-hub-overview) 에서 앱 등록
2. **이용 API** 에 *검색* 8종 + *검색어 트렌드(Search Trend)* 모두 신청
3. 루트의 `.env` 에 값 입력 (템플릿: `config/.env.example`)

```
NAVER_API_PLATFORM=apihub
NAVER_CLIENT_ID=발급받은_client_id
NAVER_CLIENT_SECRET=발급받은_client_secret
```

키가 없거나 인증에 실패하면 대시보드 대신 설정 안내 화면이 표시됩니다.

## 실행

```powershell
uv run streamlit run src/app.py
```

브라우저에서 <http://localhost:8501> 접속.

## 대시보드 구성

**전역 탭**

| 탭 | 내용 |
|---|---|
| 📋 개요 | 수집 요약 · 버티컬별 성공/실패 상태 · 검색어×버티컬 문서 수 |
| 🔀 교차분석 | 버티컬 간 문서량·게시량·키워드 자카드 유사도, 전역 상위 키워드/워드클라우드 (그래프 5·표 5) |
| 📈 검색어 트렌드 | 데이터랩 상대 검색량 비교 · 이동평균 · 기술통계 · 기간×검색어 피봇 |
| 💾 원본·엑셀 | 버티컬별 원본 CSV + **xlsx 통합 내보내기**(원본·기술통계·피봇·트렌드 시트) |

**검색 항목별 심층 탭** (수집된 버티컬만 노출)

- **텍스트형**(뉴스·블로그·카페글·웹문서·지식iN·백과사전): 공통 템플릿
  - 그래프 7 — 검색어별 문서 수 / 제목·본문 길이 박스 / 게시량 추이(뉴스·블로그) 또는 도메인 트리맵 /
    상위 출처 누적 막대 / 요일·시간대 히트맵 / 상위 명사 막대 / 제목↔본문 길이 산점도(+회귀선)
  - 표 7 — 기술통계(왜도·첨도) / 검색어별 요약 피봇 / 검색어×길이구간 교차표+카이제곱 /
    상위 출처(비중·검색어 분해) / 상위 명사 TF·편중도 / **통계 검정 요약**(Kruskal–Wallis·카이제곱·Spearman) /
    검색어 포함률 + 일자별 게시량 피봇
- **지역**: 업종·시군구 분포, 업종×검색어 히트맵, 좌표 산점도, folium 지도, 필드 보유율 + 표 6
- **이미지**: 해상도 산점도, 종횡비 분포, 방향 분류, 메가픽셀 박스, 해상도구간×검색어 히트맵 + 표 5 + 썸네일

> 파이차트는 쓰지 않습니다(막대·히스토그램·박스·바이올린·꺾은선·영역·산점도·히트맵·트리맵).
> 색상은 색각이상 대응 팔레트(Carto Safe / Viridis)로 고정됩니다.

## 사용법

- 사이드바에 검색어를 `,` 로 구분해 입력 (검색 최대 10개, 트렌드 비교는 앞 5개)
- 기간 프리셋(7/30/90일·1년) 또는 직접 선택
- **기간 필터는 뉴스·블로그에만 적용**됩니다. 검색 API 자체에 기간 파라미터가 없어
  나머지 버티컬은 최신/정확도순 상위 N건을 가져옵니다. 자세한 제약·지표 정의는 [docs/notes.md](docs/notes.md).
- "데이터 수집 실행" → 탭별 EDA 확인. 무거운 계산(형태소 분석 등)은 캐시되어 재방문 시 즉시 표시됩니다.

# Tableau MCP (Model Context Protocol) 공식 가이드

> 공식 문서: https://tableau.github.io/tableau-mcp/docs/intro  
> GitHub: https://github.com/tableau/tableau-mcp

---

## 목차

1. [개요 및 설정 방법](#1-개요-및-설정-방법)
   - [1.1 개요](#11-개요)
   - [1.2 사전 요구 사항](#12-사전-요구-사항)
   - [1.3 PAT 발급](#13-pat-발급)
   - [1.4 Claude Desktop 설치 및 연동](#14-claude-desktop-설치-및-연동)
   - [1.5 설정 파라미터](#15-설정-파라미터)
   - [1.6 엔터프라이즈 배포](#16-엔터프라이즈-배포)
2. [프롬프트](#2-프롬프트)
   - [2.1 stale-content-cleanup-inform](#21-stale-content-cleanup-inform)
   - [2.2 stale-content-cleanup-apply](#22-stale-content-cleanup-apply)
   - [2.3 job-optimization-inform](#23-job-optimization-inform)
3. [툴 정리](#3-툴-정리)
   - [3.1 Data Q&A](#31-data-qa)
   - [3.2 Workbooks](#32-workbooks)
   - [3.3 Views](#33-views)
   - [3.4 Pulse](#34-pulse)
   - [3.5 Content Exploration](#35-content-exploration)
   - [3.6 Tasks](#36-tasks)
   - [3.7 Admin Insights](#37-admin-insights)
   - [3.8 Token Management](#38-token-management)
   - [3.9 Jobs / Projects / Users](#39-jobs--projects--users)
4. [추가 주요 기능](#4-추가-주요-기능)
   - [4.1 Feature Flags](#41-feature-flags)
   - [4.2 Admin Tools (ADMIN_TOOLS_ENABLED)](#42-admin-tools-admin_tools_enabled)
   - [4.3 파괴적 작업의 2단계 안전 메커니즘](#43-파괴적-작업의-2단계-안전-메커니즘)
   - [4.4 배포 옵션 (Docker / Node SEA / Heroku)](#44-배포-옵션-docker--node-sea--heroku)
   - [4.5 개발자 도구](#45-개발자-도구)
5. [유의사항](#5-유의사항)

---

## 1. 개요 및 설정 방법

### 1.1 개요

Tableau MCP는 Tableau가 공개한 **오픈소스 MCP(Model Context Protocol) 서버**다. Claude Desktop, Cursor 등 MCP를 지원하는 AI 도구가 Tableau의 데이터 소스·워크북·Pulse 메트릭에 자연어로 접근할 수 있도록 브리지 역할을 한다.

**핵심 특징**

| 항목 | 내용 |
|---|---|
| 프로토콜 | Model Context Protocol (MCP) 표준 |
| 데이터 접근 | VizQL Data Service (VDS) API |
| 메타데이터 | Tableau Metadata API |
| Pulse | Tableau Pulse REST API |
| 지원 플랫폼 | Tableau Cloud, Tableau Server |
| 지원 AI 도구 | Claude Desktop, Cursor, 기타 MCP 호환 클라이언트 |

**제공 기능 범주**

- 데이터 소스 목록 조회 및 데이터 Q&A
- 워크북 / 뷰 탐색 및 이미지·CSV 내보내기
- Pulse 메트릭 조회 및 AI 인사이트 생성
- 콘텐츠 전체 검색
- 관리자 전용: 추출 새로 고침 작업 관리, 오래된 콘텐츠 정리, Admin Insights 쿼리

---

### 1.2 사전 요구 사항

**Tableau 측**

- **게시된 데이터 소스(Published Data Source)** 에만 적용 가능
- Tableau Server는 **VizQL Data Service(VDS)** 와 **Metadata API** 가 활성화되어 있어야 함
- 사용할 데이터 소스에 **API Access** 권한 부여 필요
  - 경로: `데이터 소스 → 권한(Permission) 다이얼로그 → API Access 체크`
- Pulse 기능 사용 시 **Tableau Pulse 활성화** 필요 (Tableau Cloud 한정)

**접속 정보**

| 항목 | 예시 |
|---|---|
| 서버 URL | `https://10ax.online.tableau.com` |
| 사이트 이름 | `my-site` (Tableau Cloud 필수, Server는 기본 사이트면 생략 가능) |
| PAT 이름 | `my-token-name` |
| PAT 값 | `xxxxxxxxxxxxxxxxxxxx` |

---

### 1.3 PAT 발급

1. Tableau Cloud/Server에 로그인
2. 우측 상단 프로필 메뉴 → **My Account Settings** 이동
3. **Personal Access Tokens** 섹션에서 토큰 생성
4. 토큰 값을 즉시 복사해 저장 (생성 직후 한 번만 표시됨)

> **주의:** PAT는 **15일 미사용 시 자동 만료**된다.

---

### 1.4 Claude Desktop 설치 및 연동

**방법 A — Claude Marketplace (권장)**

1. Claude Desktop 설치 (claude.ai/download)
2. `Settings → Extensions → Browse Extensions`
3. "Tableau" 검색 후 설치
4. 프롬프트에 따라 SERVER / SITE_NAME / PAT_NAME / PAT_VALUE 입력

**방법 B — GitHub Release**

1. [GitHub Releases](https://github.com/tableau/tableau-mcp) 에서 `.mcpb` 파일 다운로드
2. `Settings → Extensions` → 파일 드래그 앤 드롭
3. 파라미터 입력

**연결 검증**

```
list some of the Tableau datasources
```

위 문장으로 채팅을 시작해 데이터 소스 목록이 반환되면 연결 성공.

---

### 1.5 설정 파라미터

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `SERVER` | ✅ | Tableau Cloud pod URL 또는 Server 호스트명 |
| `SITE_NAME` | Cloud: ✅ / Server: 선택 | Cloud는 필수; Server는 기본 사이트면 공백 |
| `PAT_NAME` | ✅ | PAT의 이름 (이메일 주소 아님) |
| `PAT_VALUE` | ✅ | PAT 발급 시 복사한 토큰 값 |
| `MAX_RESULT_LIMIT` | 선택 | 쿼리 결과 최대 행 수 제한 |
| `ADMIN_TOOLS_ENABLED` | 선택 | `true` 설정 시 관리자 전용 툴 활성화 |
| `STALE_CONTENT_MIN_AGE_DAYS` | 선택 | 오래된 콘텐츠 기준일 수 (기본값 90) |
| `INCLUDE_PROJECT_IDS` | 선택 | 관리 범위 프로젝트 LUID 목록 |
| `DISABLE_METADATA_API_REQUESTS` | 선택 | Metadata API 호출 비활성화 |
| `DISABLE_QUERY_DATASOURCE_VALIDATION_REQUESTS` | 선택 | 쿼리 유효성 검사 비활성화 |

---

### 1.6 엔터프라이즈 배포

Tableau MCP는 **플러그인 기반 구조**로 텔레메트리·모니터링을 조직 인프라에 맞게 구성할 수 있다.

| 배포 옵션 | 내용 |
|---|---|
| **Tableau Server** | 전용 고객 배포 가이드 제공 |
| **Tableau Cloud (2026.2 예정)** | 클라우드 호스팅 셀프 서비스 배포, OAuth 지원 포함 |
| **Self-hosted** | 인프라 직접 제어, 도메인 URL 커스터마이징 가능 |

**인증 방식:** OAuth 기반. 사용자가 Tableau 로그인으로 인가 후 연결. 조직의 보안·Identity 정책 그대로 적용.

---

## 2. 프롬프트

프롬프트는 여러 툴을 조율하는 **가이드형 관리자 워크플로우**다. `ADMIN_TOOLS_ENABLED=true` 및 관리자 권한이 필요하다.

---

### 2.1 stale-content-cleanup-inform

**목적:** 오래된 워크북 및 게시된 데이터 소스를 식별해 보고서로 출력 (읽기 전용)

**특징**
- 삭제·태깅·알림 등 변경 작업 없음
- `get-stale-content-report` 툴을 한 번 호출해 서버 측 필터링 결과를 Markdown 테이블로 출력

**파라미터**

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `minAgeDays` | 정수 (문자열) | 비활성 기준일 수 (기본값: 서버 설정 90일) |
| `projectIds` | 문자열 | 쉼표로 구분된 프로젝트 LUID 목록 |

> 이 프롬프트는 `stale-content-cleanup-apply` 와 쌍으로 사용한다.

---

### 2.2 stale-content-cleanup-apply

**목적:** 오래된 콘텐츠를 식별하고, 소유자 알림 정보를 보고한 뒤, **명시적 인간 승인 후** 삭제를 실행하는 7단계 워크플로우

**안전 장치**
- 1~3단계는 읽기 전용 (데이터 수집·보고)
- 4단계에서 **사람의 명시적 승인** 대기
- 서버 측 태그 재검증 후에만 삭제 실행
- `dryRun: true` 설정 시 승인 단계까지만 진행 (실제 삭제 없음)

**파라미터**

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `minAgeDays` | 정수 (문자열) | 비활성 기준일 수 |
| `projectIds` | 문자열 | 범위를 좁힐 프로젝트 LUID 목록 |
| `itemTypes` | 문자열 | `Workbook`, `Datasource`, 또는 둘 다 |
| `tag` | 문자열 | 삭제 예정 태그명 (기본값: `pending-deletion`) |
| `dryRun` | boolean | `true` 시 승인 후 실제 삭제 생략 |

---

### 2.3 job-optimization-inform

**목적:** Tableau Cloud의 Admin Insights 잡 성능 데이터를 분석해 최적화 기회를 도출 (읽기 전용)

**워크플로우**
1. `query-admin-insights-job-performance` 툴 호출
2. 결과를 Markdown 테이블로 포맷
3. "Optimization signals" 섹션에서 성능 인사이트 정리
4. 기본값: 추출 새로 고침(extract-refresh) 잡 유형 분석

**파라미터**

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `jobType` | 문자열 | 분석할 잡 유형 (기본값: extract-refresh) |
| `lookbackDays` | 정수 | 분석 기간 (최대 90일; Advanced Management 시 365일) |
| `limit` | 정수 | 쿼리당 최대 반환 행 수 |
| `discover` | boolean | `true` 시 사이트 내 모든 잡 유형 자동 열거·분석 |

---

## 3. 툴 정리

### 3.1 Data Q&A

데이터 소스 조회 및 쿼리 핵심 툴 그룹.

---

#### `list-datasources` — 데이터 소스 목록 조회

게시된 데이터 소스 목록을 반환한다.

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `filter` | string | 선택 | Tableau REST API 필터 구문 (예: `name:eq:Project Views`) |
| `pageSize` | integer | 선택 | API 호출당 반환 수 (100개 이상 환경에서 유용) |
| `limit` | integer | 선택 | 총 반환 최대 수 (`MAX_RESULT_LIMIT` 준수) |

**출력 예시**
```json
[{
  "id": "2d935df8-fe7e-4fd8-bb14-35eb4ba31d45",
  "name": "Superstore Datasource",
  "description": "Overview...",
  "project": {
    "name": "Samples",
    "id": "cbec32db-a4a2-4308-b5f0-4fc67322f359"
  }
}]
```

---

#### `get-datasource-metadata` — 데이터 소스 메타데이터 조회

데이터 소스의 설명, 논리 테이블 모델, 필드 목록, Tableau 파라미터를 반환한다.

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `datasourceLuid` | string | ✅ | 데이터 소스 LUID (`list-datasources`로 확인) |

**출력 구조**

| 키 | 설명 |
|---|---|
| `datasourceDescription` | 메타데이터 및 사용 설명 |
| `datasourceModel` | 논리 테이블·관계 (Tableau 2025.3+ 전용) |
| `fieldGroups` | 논리 테이블별로 묶인 필드 목록 |
| `parameters` | 파라미터 목록 (타입·제약 조건 포함) |

각 필드 포함 정보: `name`, `dataType`, `columnClass`, `logicalTableId`, `defaultAggregation`, `dataCategory`, `role`

> `datasourceModel`은 Tableau 2025.3 이상에서만 반환된다.

---

#### `query-datasource` — 데이터 소스 쿼리

VizQL 쿼리를 실행해 게시된 데이터 소스에서 실제 데이터를 조회한다.

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `datasourceLuid` | string | ✅ | 데이터 소스 LUID |
| `query` | object | ✅ | VizQL 쿼리 객체 (fields, filters, sorting 포함) |
| `limit` | number | 선택 | 최대 반환 행 수 (`MAX_RESULT_LIMIT` 준수) |

**출력 예시**
```json
{
  "data": [
    {"Customer Name": "Sean Miller", "Total Revenue": 25043.05},
    {"Customer Name": "Tamara Chand", "Total Revenue": 19052.22}
  ]
}
```

> VizQL 쿼리 구조(fields, filters 등)는 [Tableau VDS 가이드](./tableau_vds_guide.md) 참고.

---

#### `delete-datasource` — 데이터 소스 삭제

⚠️ **관리자 전용 (`ADMIN_TOOLS_ENABLED=true` 필요) · 파괴적 작업**

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `datasourceId` | string | ✅ | 삭제할 데이터 소스 LUID |
| `confirm` | boolean | 선택 | `true` 시 영구 삭제 실행, 생략/`false` 시 미리 보기 모드 |
| `tag` | string | 선택 | 삭제 예정 태그명 (기본값: `pending-deletion`) |

**2단계 동작**
1. **미리 보기 (기본):** `pending-deletion` 태그 부착, 의존 워크북·플로우 보고 — 삭제 없음
2. **삭제 (`confirm: true`):** 서버에서 태그 재확인 후 영구 삭제

> Tableau Cloud: 휴지통 이동 (복원 기간 한정) | Tableau Server: 즉시 영구 삭제

---

### 3.2 Workbooks

---

#### `list-workbooks` — 워크북 목록 조회

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `filter` | string | 선택 | 필터 구문 (예: `name:eq:Superstore`) |
| `pageSize` | integer | 선택 | API 호출당 반환 수 |
| `limit` | integer | 선택 | 총 반환 최대 수 |

출력 필드: `id`, `name`, `webpageUrl`, `contentUrl`, `project`, `showTabs`, `defaultViewId`, `tags`

---

#### `get-workbook` — 워크북 상세 조회

워크북 메타데이터와 포함된 뷰 목록·사용 통계를 반환한다.

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `workbookId` | string | ✅ | 워크북 ID (`list-workbooks`로 확인) |

출력: 워크북 메타데이터 + `views[]` (id, name, 타임스탬프, `usage.totalViewCount` 포함)

---

#### `delete-workbook` — 워크북 삭제

⚠️ **관리자 전용 · 파괴적 작업**

`delete-datasource`와 동일한 2단계 방식으로 동작.

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `workbookId` | string | ✅ | 삭제할 워크북 LUID |
| `confirm` | boolean | 선택 | `true` 시 영구 삭제 |
| `tag` | string | 선택 | 삭제 예정 태그명 (기본값: `pending-deletion`) |

---

### 3.3 Views

---

#### `list-views` — 뷰 목록 조회

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `filter` | string | 선택 | 필터 구문 (예: `name:eq:Overview`) |
| `pageSize` | integer | 선택 | API 호출당 반환 수 |
| `limit` | integer | 선택 | 총 반환 최대 수 |

출력 필드: `id`, `name`, `createdAt`, `updatedAt`, `workbook`, `owner`, `project`, `tags`, `usage.totalViewCount`

---

#### `get-view-image` — 뷰 이미지 조회

지정한 뷰의 렌더링 이미지를 반환한다.

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `viewId` | string | ✅ | 뷰 ID |
| `width` | integer | 선택 | 이미지 너비 (픽셀) |
| `height` | integer | 선택 | 이미지 높이 (픽셀) |
| `format` | enum | 선택 | `PNG` (기본값, 전 버전 호환) \| `SVG` (Server 2026.2+ 전용) |
| `viewFilters` | object | 선택 | 뷰에 적용할 필터 (`{"year": "2017"}`) |

> PNG는 데이터 분석·해석 용도, SVG는 표시·임베딩 용도에 적합.

---

#### `get-view-data` — 뷰 데이터 CSV 조회

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `viewId` | string | ✅ | 뷰 ID |
| `viewFilters` | object | 선택 | 필드명 → 값 매핑 (`vf_` 접두사 자동 처리) |

출력: CSV 형식 데이터

---

#### `list-custom-views` — 커스텀 뷰 목록 조회

워크북에 저장된 커스텀 뷰(사용자 지정 상태) 목록을 반환한다.

---

#### `get-custom-view-data` — 커스텀 뷰 CSV 조회

지정한 커스텀 뷰의 데이터를 CSV로 반환한다.

---

#### `get-custom-view-image` — 커스텀 뷰 이미지 조회

지정한 커스텀 뷰의 렌더링 이미지를 반환한다.

---

### 3.4 Pulse

Tableau Pulse 메트릭 조회 및 AI 인사이트 생성 툴 그룹.

---

#### `list-all-pulse-metric-definitions` — 전체 Pulse 메트릭 정의 조회

사이트에 게시된 모든 Pulse 메트릭 정의 목록을 반환한다.

---

#### `list-pulse-metric-definitions-from-definition-ids` — 특정 메트릭 정의 조회

메트릭 정의 ID 목록으로 특정 정의를 조회한다.

---

#### `list-pulse-metrics-from-metric-definition-id` — 정의별 메트릭 조회

하나의 메트릭 정의 ID로 해당 정의에 속한 Pulse 메트릭 목록을 반환한다.

---

#### `list-pulse-metrics-from-metric-ids` — 메트릭 ID 목록으로 조회

메트릭 ID 목록으로 특정 Pulse 메트릭들을 반환한다.

---

#### `list-pulse-metric-subscriptions` — 현재 사용자 구독 메트릭 목록

현재 사용자가 구독 중인 Pulse 메트릭 구독 목록을 반환한다.

---

#### `generate-pulse-metric-value-insight-bundle` — 인사이트 번들 생성

Pulse 메트릭의 현재 집계 값에 대한 인사이트 번들을 생성한다.

**입력 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `bundleRequest` | object | ✅ | 버전, 옵션, 인풋(데이터 소스·필드·시간 차원·필터) 포함 |
| `bundleType` | enum | 선택 | `ban` (기본) \| `basic` \| `springboard` \| `detail` |

**bundleType 비교**

| 타입 | 포함 내용 |
|---|---|
| `ban` | 현재 집계 값 + 기간 대비 변화 |
| `springboard` | 현재 값 + 기간 대비 변화 + 상위 인사이트 1개 |
| `basic` | springboard와 유사, 낮은 대역폭 차원 중심 |
| `detail` | 트렌드·기여 요소 포함 종합 성능 분석 |

출력: `insight_groups`, `insights` (Vega-Lite 시각화 스펙 포함), `summaries`, `has_errors`

---

#### `generate-pulse-insight-brief` — Pulse AI 인사이트 브리프 생성

자연어 질문에 기반해 Pulse 메트릭에 대한 AI 대화형 응답을 생성한다. 멀티턴 대화 지원.

**입력 파라미터 (`briefRequest`)**

| 파라미터 | 설명 |
|---|---|
| `language` | 응답 언어 (예: `LANGUAGE_EN_US`) |
| `locale` | 포맷 로케일 (예: `LOCALE_EN_US`) |
| `messages` | 대화 메시지 배열 (role: USER/ASSISTANT) |
| `now` | 현재 시각 (`YYYY-MM-DD HH:MM:SS`) |
| `time_zone` | 타임존 참조 |

메시지 `action_type`: `ACTION_TYPE_ANSWER` | `ACTION_TYPE_SUMMARIZE` | `ACTION_TYPE_ADVISE`

출력: `markup` (AI 생성 Markdown), `source_insights` (Vega-Lite 시각화), `follow_up_questions`, `not_enough_information`

> Slack, Teams, ChatGPT, Claude 등 채팅 인터페이스에 최적화.

---

### 3.5 Content Exploration

---

#### `search-content` — 콘텐츠 전체 검색

사이트 전체 콘텐츠를 키워드로 검색한다.

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `terms` | string | 선택 | 검색어 (생략 시 전체 검색) |
| `limit` | integer | 선택 | 반환 수 (기본값: 100, 최대: 2000) |
| `orderBy` | array | 선택 | 정렬 기준 (`hitsTotal`, `hitsSmallSpanTotal`, `hitsMediumSpanTotal`, `hitsLargeSpanTotal`, `downstreamWorkbookCount`) |
| `filter` | object | 선택 | `contentTypes`, `ownerIds`, `modifiedTime` 로 필터 |

지원 콘텐츠 타입: `lens`, `datasource`, `virtualconnection`, `collection`, `project`, `flow`, `datarole`, `table`, `database`, `view`, `workbook`

---

### 3.6 Tasks

⚠️ **관리자 전용 (`ADMIN_TOOLS_ENABLED=true` 필요)**

---

#### `list-extract-refresh-tasks` — 추출 새로 고침 작업 목록

사이트의 추출 새로 고침 작업 전체를 반환한다.

- 파라미터 없음
- 출력: 작업 ID, 대상 데이터 소스/워크북 ID, 스케줄 세부 정보(빈도·다음 실행 시간)
- REST API가 필터·페이지네이션을 지원하지 않아 전체 반환

---

#### `delete-extract-refresh-task` — 추출 새로 고침 작업 삭제

⚠️ **파괴적 작업**

예약된 추출 새로 고침을 영구 삭제한다.

---

#### `update-cloud-extract-refresh-task` — 추출 새로 고침 스케줄 변경

**Tableau Cloud 전용.** 기존 작업을 삭제하지 않고 스케줄을 변경한다.

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `taskId` | string (UUID) | ✅ | 수정할 작업 ID |
| `schedule` | object | ✅ | 새 스케줄 설정 (기존 스케줄 전체 대체) |

**schedule 객체 구조**

```json
{
  "frequency": "Weekly",
  "frequencyDetails": {
    "start": "06:00:00",
    "intervals": {
      "interval": [{ "weekDay": "Monday" }]
    }
  }
}
```

- `frequency`: `Hourly` | `Daily` | `Weekly` | `Monthly`
- `start` 시간: `HH:mm:ss` 형식, 5분 단위 정렬 필수
- Hourly는 `end` 필드 필수; Daily/Weekly/Monthly는 생략

---

### 3.7 Admin Insights

⚠️ **관리자 전용 (`ADMIN_TOOLS_ENABLED=true` 필요)**  
VDS를 통해 Tableau Cloud Admin Insights 데이터 소스를 직접 쿼리한다.

---

#### `query-admin-insights-ts-events` — TS Events 쿼리

콘텐츠·사용자의 액세스(Access), 게시(Publish), 업데이트(Update), 삭제(Delete) 이벤트를 조회한다.

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `query` | object | ✅ | VDS 쿼리 객체 (fields, filters) |
| `limit` | integer | 선택 | 최대 반환 행 수 |

- 조회 기간: 기본 90일 / Advanced Management 시 365일
- 필드 캡션 주의: `Item Id` (대소문자 그대로 사용)

---

#### `query-admin-insights-site-content` — Site Content 쿼리

워크북·데이터 소스·뷰·플로우·프로젝트의 전체 콘텐츠 인벤토리를 조회한다. 한 번도 접근되지 않은 콘텐츠도 포함.

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `query` | object | ✅ | VDS 쿼리 객체 |
| `limit` | integer | 선택 | 최대 반환 행 수 |

출력 필드 예: `Item ID`, `Item Type`, `Item Name`, `Owner Email`, `Created At`, `Updated At`, `Last Accessed At` (null = 미접근), `Size`

---

#### `get-stale-content-report` — 오래된 콘텐츠 보고서

비활성 콘텐츠를 서버 측에서 필터링해 결정론적 보고서를 반환한다.

| 파라미터 | 타입 | 범위 | 설명 |
|---|---|---|---|
| `minAgeDays` | integer | 1–3650 | 비활성 기준일 수 (기본값: 90) |
| `projectIds` | array | — | 범위를 좁힐 프로젝트 LUID 목록 |
| `itemTypes` | array | — | `Workbook`, `Datasource` |

출력: `thresholdDays`, `totalStaleItems`, `totalStaleSizeBytes`, `rows[]` (itemId, itemType, itemName, project, ownerEmail, daysSinceLastUse, size, neverAccessed 포함)

---

#### `query-admin-insights-job-performance` — Job Performance 쿼리

추출 새로 고침 등 잡 성능 데이터를 조회한다.

---

### 3.8 Token Management

---

#### `reset-consent` — OAuth 동의 초기화

현재 사용자의 Tableau 인가 서버에 저장된 OAuth 동의를 초기화한다.

---

#### `revoke-access-token` — 액세스 토큰 폐기

현재 MCP 세션에서 사용 중인 액세스 토큰을 즉시 폐기한다.

---

### 3.9 Jobs / Projects / Users

> 각 카테고리는 현재 1개의 툴만 포함되어 있으며, 상세 파라미터는 공식 문서에서 확인.

| 카테고리 | 툴 수 | 주요 기능 |
|---|---|---|
| Jobs | 1 | 잡 목록 조회 |
| Projects | 1 | 프로젝트 목록 조회 |
| Users | 1 | 사용자 목록 조회 |

---

## 4. 추가 주요 기능

### 4.1 Feature Flags

`features.json` (프로젝트 루트)으로 기능 활성화 여부를 제어한다.

```json
{
  "mcpapps": true,
  "pulse": true,
  "oauth-embedded": false
}
```

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `mcpapps` | true | MCP 앱 통합 활성화 |
| `pulse` | true | Pulse 메트릭 툴 활성화 |
| `oauth-embedded` | false | 임베디드 OAuth 활성화 (엔터프라이즈 배포용) |

- 파일 누락·파싱 오류 시 **모든 기능 비활성화** 및 오류 로그 출력
- 목록에 없는 플래그는 기본 비활성화

---

### 4.2 Admin Tools (ADMIN_TOOLS_ENABLED)

환경 변수 `ADMIN_TOOLS_ENABLED=true` 설정 시 아래 툴이 등록된다.

| 그룹 | 활성화 툴 |
|---|---|
| Data Q&A | `delete-datasource` |
| Workbooks | `delete-workbook` |
| Tasks | `list-extract-refresh-tasks`, `delete-extract-refresh-task`, `update-cloud-extract-refresh-task` |
| Admin Insights | `query-admin-insights-ts-events`, `query-admin-insights-site-content`, `get-stale-content-report`, `query-admin-insights-job-performance` |
| Prompts | `stale-content-cleanup-inform`, `stale-content-cleanup-apply`, `job-optimization-inform` |

모든 Admin 툴은 요청 시점에 **사이트 역할을 재검증**한다.  
허용 역할: `SiteAdministratorCreator`, `SiteAdministratorExplorer`, `ServerAdministrator`

---

### 4.3 파괴적 작업의 2단계 안전 메커니즘

삭제류 툴(`delete-datasource`, `delete-workbook`)은 실수로 인한 영구 삭제를 방지하기 위해 2단계 구조를 사용한다.

```
1단계 (기본: confirm 생략 또는 false)
  → pending-deletion 태그 부착 (Tableau UI에서 확인 가능)
  → 의존성 보고 (연결된 워크북·플로우 목록 출력)
  → 실제 삭제 없음 (가역적)

      ↓ 사람이 검토·승인

2단계 (confirm: true)
  → 서버에서 pending-deletion 태그 재확인
  → 태그 존재 확인 후 영구 삭제 실행
  → Tableau Cloud: 휴지통 이동 | Tableau Server: 즉시 영구 삭제
```

> 에이전트가 두 단계를 자동으로 연속 실행하는 것을 기술적으로 막지는 않는다. 워크플로우에서 인간 승인 단계를 명시적으로 강제해야 한다.

---

### 4.4 배포 옵션 (Docker / Node SEA / Heroku)

| 방식 | 내용 |
|---|---|
| **Docker** | GitHub Container Registry 이미지 사용 (`ghcr.io/tableau/tableau-mcp`) |
| **Node.js SEA** | Node.js Single Executable Application으로 패키징 — 의존성 없이 단일 바이너리 배포 |
| **Heroku** | 실험적 Heroku 배포 지원 |

---

### 4.5 개발자 도구

| 도구 | 설명 |
|---|---|
| **MCP Inspector** | 설정 정확성 검증, 툴 동작 확인 |
| **Building From Source** | 소스 직접 빌드 방법 |
| **Debugging** | `TRANSPORT=http` 환경 변수 설정으로 HTTP 모드 디버깅 |
| **Unit Tests** | Vitest 기반 (`src/` 디렉터리 내 테스트 파일) |
| **E2E Tests** | Vitest 기반 통합 테스트 |
| **Eval Tests** | 기능 평가 테스트 |
| **Contributing** | 오픈소스 기여 가이드라인 |

---

## 5. 유의사항

### 인증·권한

- PAT는 **15일 미사용 시 자동 만료**된다. 만료 시 새 PAT 발급 후 재설정 필요.
- `PAT_NAME`은 이메일 주소가 아닌 **토큰 이름**을 입력해야 한다. (401 에러 주의)
- 데이터 소스에 **API Access 권한** 미부여 시 403 에러 발생.
- Admin 툴은 요청마다 사이트 역할을 재검증한다. 권한이 변경되면 즉시 차단.

### 데이터 소스 제한

- **게시된(Published) 데이터 소스만** 지원. 워크북에 내장(embedded)된 데이터 소스 직접 쿼리 불가.
- Cube 데이터 소스 미지원 (VDS 동일 제한).

### 플랫폼별 차이

| 기능 | Tableau Cloud | Tableau Server |
|---|---|---|
| Pulse | ✅ 지원 | ❌ 미지원 |
| Admin Insights | ✅ 지원 | 제한적 |
| `update-cloud-extract-refresh-task` | ✅ 지원 | ❌ Cloud 전용 |
| VDS | ✅ 지원 | 2025.1 이상 필요 |
| `datasourceModel` 반환 | 2025.3+ 필요 | 2025.3+ 필요 |
| 삭제 후 처리 | 휴지통 이동 | 즉시 영구 삭제 |

### 쿼리 제한

- `MAX_RESULT_LIMIT` 환경 변수가 설정되어 있으면 모든 쿼리 결과가 해당 값으로 제한된다.
- Admin Insights 조회 기간: 기본 90일, Advanced Management 구독 시 365일.
- 추출 새로 고침 작업 목록은 REST API 제한으로 필터·페이지네이션 미지원 — 전체 목록 반환.

### 삭제 작업 주의

- `delete-workbook` / `delete-datasource`의 2단계 안전장치는 **기술적 강제가 아닌 프롬프트 수준의 기대**다. AI 에이전트가 두 단계를 연속 실행할 수 있으므로 워크플로우 설계 시 인간 승인 단계를 명시적으로 포함해야 한다.
- `stale-content-cleanup-apply` 사용 시 반드시 `dryRun: true`로 먼저 테스트 후 실행할 것.

### 이미지 포맷

- `get-view-image`의 `SVG` 포맷은 **Tableau Server 2026.2 (REST API v3.29) 이상**에서만 사용 가능.
- PNG는 AI 모델이 이미지를 분석할 때, SVG는 사용자에게 표시·임베딩할 때 사용.

### 트러블슈팅

| 증상 | 원인 및 해결 |
|---|---|
| 401 Unauthorized | 서버 URL, 사이트명 확인; `PAT_NAME`이 토큰 이름인지 확인 (이메일 아님) |
| 403 Forbidden | 데이터 소스 API Access 권한 부여 확인 |
| Admin 툴 미노출 | `ADMIN_TOOLS_ENABLED=true` 환경 변수 설정 확인 |
| datasourceModel 없음 | Tableau 버전 2025.3 이상인지 확인 |
| Pulse 툴 없음 | `features.json`에서 `"pulse": true` 확인 |
| 결과 잘림 | `MAX_RESULT_LIMIT` 값 상향 조정 |

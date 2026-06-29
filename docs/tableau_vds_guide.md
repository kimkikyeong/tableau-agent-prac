# Tableau VizQL Data Service (VDS) 가이드

> 공식 문서: https://help.tableau.com/current/api/vizql-data-service/en-us/index.html  
> 최초 공개: 2025.1 (2025년 2월) | 최신 버전: 2026.1 (2026년 2월)

---

## 목차

1. [VDS 개요](#1-vds-개요)
2. [VDS 설정법](#2-vds-설정법)
3. [VDS 메소드 정리](#3-vds-메소드-정리)
   - [3.1 read-metadata (데이터 소스 메타데이터 조회)](#31-read-metadata-데이터-소스-메타데이터-조회)
   - [3.2 read-datasource-model (데이터 소스 모델 조회)](#32-read-datasource-model-데이터-소스-모델-조회)
   - [3.3 query-datasource (데이터 쿼리)](#33-query-datasource-데이터-쿼리)
4. [주요 기능 정리](#4-주요-기능-정리)
   - [4.1 필드(Fields) 지정](#41-필드fields-지정)
   - [4.2 필터(Filters) 유형](#42-필터filters-유형)
   - [4.3 테이블 계산(Table Calculations)](#43-테이블-계산table-calculations)
   - [4.4 파라미터 오버라이드](#44-파라미터-오버라이드)
   - [4.5 응답 옵션(Options)](#45-응답-옵션options)
   - [4.6 SSE 스트리밍 (2026.1+)](#46-sse-스트리밍-20261)
5. [에러 코드](#5-에러-코드)
6. [유의사항 및 제한](#6-유의사항-및-제한)
7. [버전 히스토리](#7-버전-히스토리)

---

## 1. VDS 개요

VizQL Data Service(VDS)는 Tableau 시각화 없이 **게시된 데이터 소스(Published Data Source)에서 직접 데이터를 조회**할 수 있는 REST API다. BI 대시보드를 거치지 않고 Tableau의 데이터 모델·계산 필드·파라미터를 그대로 활용해 프로그래밍 방식으로 데이터를 추출할 수 있다.

**적용 환경**

| 플랫폼 | 지원 버전 |
|---|---|
| Tableau Cloud | 전체 |
| Tableau Server | 2025.1 이상 |

**Base URL 패턴**

```
# Tableau Cloud
https://{pod}.online.tableau.com/api/v1/vizql-data-service/{method}

# Tableau Server
https://{server}/api/v1/vizql-data-service/{method}
```

---

## 2. VDS 설정법

### 2.1 인증 방식

VDS는 모든 요청에 **인증 토큰**이 필요하다. Tableau REST API Sign In으로 발급받은 토큰을 `X-Tableau-Auth` 헤더에 포함한다.

| 인증 방식 | 설명 |
|---|---|
| **PAT (Personal Access Token)** | 권장. `tokenName` + `tokenValue`로 REST API 로그인 후 토큰 발급 |
| **JWT (JSON Web Token)** | scope: `"tableau:viz_data_service:read"` 설정 필수 |
| **Username / Password** | 기본 자격증명 방식 |

**PAT 로그인 예시 (REST API)**

```http
POST https://{server}/api/3.x/auth/signin
Content-Type: application/json

{
  "credentials": {
    "personalAccessTokenName": "my-token-name",
    "personalAccessTokenSecret": "my-token-secret",
    "site": { "contentUrl": "my-site" }
  }
}
```

응답의 `credentials.token` 값을 이후 VDS 요청 헤더에 사용한다.

### 2.2 데이터 소스 권한 설정

VDS로 쿼리하려면 해당 데이터 소스에 **API Access 권한**이 부여되어 있어야 한다.

> Tableau UI: `데이터 소스 → 권한(Permission) 다이얼로그 → API Access 체크`

### 2.3 datasourceLuid 확인 방법

모든 VDS 메소드에는 `datasourceLuid`(UUID)가 필수다.

**방법 1 — UI**
```
Explore → All Data Sources → 데이터 소스 선택 → Details 아이콘
→ Data Source Details 화면 하단에서 확인
```

**방법 2 — REST API**
```http
GET https://{server}/api/3.x/sites/{siteId}/datasources
```
응답의 `datasource[].id` 값이 LUID다.

### 2.4 요청 헤더 공통 구조

```http
POST https://{server}/api/v1/vizql-data-service/{method}
Content-Type: application/json
X-Tableau-Auth: {token}
```

---

## 3. VDS 메소드 정리

### 3.1 read-metadata (데이터 소스 메타데이터 조회)

게시된 데이터 소스의 **필드 목록, 계산 필드, 파라미터 정보**를 반환한다.

**엔드포인트**
```
POST /api/v1/vizql-data-service/read-metadata
```

**요청 본문**

```json
{
  "datasource": {
    "datasourceLuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "options": {
    "bypassMetadataCache": false,
    "interpretFieldCaptionsAsFieldNames": false,
    "includeHiddenFields": false,
    "includeGroupFormulas": false
  }
}
```

**응답 구조**

| 객체 | 필드 | 설명 |
|---|---|---|
| `data[]` | `fieldName` | 필드 내부 이름 |
| | `fieldCaption` | 화면 표시 이름 |
| | `dataType` | STRING, INTEGER, REAL, BOOLEAN, DATE 등 |
| | `fieldRole` | DIMENSION / MEASURE |
| | `fieldType` | DISCRETE / CONTINUOUS |
| | `defaultAggregation` | 기본 집계 방식 |
| | `formula` | 계산 필드 수식 |
| | `hidden` | 숨김 여부 |
| | `isLODCalc` | LOD 계산 여부 |
| `extraData.parameters[]` | `parameterCaption` | 파라미터 표시 이름 |
| | `dataType` | 파라미터 데이터 타입 |
| | `value` | 현재 값 |
| | `min` / `max` / `step` | 범위 설정 |
| | `members[]` | 허용 목록 |

---

### 3.2 read-datasource-model (데이터 소스 모델 조회)

데이터 소스의 **논리적 테이블 구조와 관계(Relationship)** 정보를 반환한다.

**엔드포인트**
```
POST /api/v1/vizql-data-service/read-datasource-model
```

**요청 본문**

```json
{
  "datasource": {
    "datasourceLuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
}
```

**응답 예시**

```json
{
  "logicalTables": [
    {
      "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862",
      "caption": "Orders"
    }
  ],
  "logicalTableRelationships": [
    {
      "fromLogicalTable": {
        "logicalTableId": "Orders_ECFCA1FB690A41FE803BC071773BA862"
      },
      "toLogicalTable": {
        "logicalTableId": "People_D73023733B004CC1B3CB1ACF62F4A965"
      }
    }
  ]
}
```

> 다중 논리 테이블이 있는 데이터 소스에서 `logicalTableId`를 확인한 뒤 `query-datasource`의 필드 지정 시 활용할 수 있다.

---

### 3.3 query-datasource (데이터 쿼리)

**핵심 메소드.** 데이터 소스에서 실제 데이터를 조회한다.

**엔드포인트**
```
POST /api/v1/vizql-data-service/query-datasource
```

**요청 본문 전체 구조**

```json
{
  "datasource": {
    "datasourceLuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "connections": [
      {
        "connectionLuid": "string",
        "connectionUsername": "string",
        "connectionPassword": "string"
      }
    ]
  },
  "query": {
    "fields": [ ... ],
    "filters": [ ... ],
    "parameters": [ ... ]
  },
  "options": { ... }
}
```

- `connections`: 자격증명이 별도로 필요한 연결에만 지정. 단일 연결은 생략 가능.
- `query.fields`: 필수. 최소 1개 이상 지정.
- `query.filters` / `query.parameters` / `options`: 선택.

**최소 요청 예시 (Ship Mode별 Sales 합계)**

```json
{
  "datasource": {
    "datasourceLuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "query": {
    "fields": [
      { "fieldCaption": "Ship Mode" },
      { "fieldCaption": "Sales", "function": "SUM", "maxDecimalPlaces": 2 }
    ]
  }
}
```

**응답 예시**

```json
{
  "data": [
    { "Ship Mode": "Second Class", "SUM(Sales)": 466671.11 },
    { "Ship Mode": "Standard Class", "SUM(Sales)": 1358215.74 }
  ]
}
```

---

## 4. 주요 기능 정리

### 4.1 필드(Fields) 지정

`query.fields` 배열에 조회할 컬럼을 정의한다. 세 가지 패턴을 지원한다.

**① 디멘전 (단순 조회)**

```json
{
  "fieldCaption": "Category",
  "sortPriority": 1,
  "sortDirection": "ASC"
}
```

**② 집계 측정값**

```json
{
  "fieldCaption": "Sales",
  "function": "SUM",
  "maxDecimalPlaces": 2,
  "fieldAlias": "총매출"
}
```

지원 집계 함수:

| 범주 | 함수 |
|---|---|
| 수치 | SUM, AVG, MEDIAN, COUNT, COUNTD, MIN, MAX, STDEV, VAR |
| 날짜 (Date Part) | YEAR, QUARTER, MONTH, WEEK, DAY |
| 날짜 (Date Trunc) | TRUNC_YEAR, TRUNC_QUARTER, TRUNC_MONTH, TRUNC_WEEK, TRUNC_DAY |
| 컬렉션 | COLLECT |

**③ 커스텀 계산 필드**

```json
{
  "fieldCaption": "Profit Margin",
  "calculation": "SUM([Profit])/SUM([Sales])"
}
```

**④ 빈(Bin) 생성**

```json
{
  "fieldCaption": "Sales",
  "binSize": 500
}
```

**필드 공통 속성**

| 속성 | 타입 | 설명 |
|---|---|---|
| `fieldCaption` | string | 필드 표시 이름 (필수) |
| `fieldAlias` | string | 응답에서 사용할 별칭 |
| `function` | string | 집계 함수 |
| `calculation` | string | Tableau 계산 수식 |
| `maxDecimalPlaces` | int (≥0) | 소수점 자릿수 |
| `sortDirection` | ASC \| DESC | 정렬 방향 |
| `sortPriority` | int | 정렬 우선순위 (낮을수록 우선) |
| `binSize` | number | 빈 크기 (on-the-fly 빈 생성) |

---

### 4.2 필터(Filters) 유형

#### SET 필터 (특정 값 포함/제외)

```json
{
  "field": { "fieldCaption": "Segment" },
  "filterType": "SET",
  "values": ["Consumer", "Home Office"],
  "exclude": false
}
```

#### QUANTITATIVE_NUMERICAL 필터 (수치 범위)

```json
{
  "column": { "fieldCaption": "Sales", "function": "SUM" },
  "filterType": "QUANTITATIVE_NUMERICAL",
  "quantitativeFilterType": "RANGE",
  "min": 1000,
  "max": 50000
}
```

`quantitativeFilterType`: `MIN` | `MAX` | `RANGE` | `ONLY_NULL` | `ONLY_NON_NULL`

#### QUANTITATIVE_DATE 필터 (날짜 범위)

```json
{
  "field": { "fieldCaption": "Order Date" },
  "filterType": "QUANTITATIVE_DATE",
  "quantitativeFilterType": "RANGE",
  "minDate": "2023-01-01",
  "maxDate": "2023-12-31"
}
```

> 날짜 형식은 **RFC 3339** 준수. 시간대(timezone) 미지원.

#### DATE 필터 (상대 날짜)

```json
{
  "field": { "fieldCaption": "Order Date" },
  "filterType": "DATE",
  "periodType": "MONTHS",
  "dateRangeType": "LASTN",
  "rangeN": 6,
  "anchorDate": "2024-06-01"
}
```

| 속성 | 옵션 |
|---|---|
| `periodType` | MINUTES, HOURS, DAYS, WEEKS, MONTHS, QUARTERS, YEARS |
| `dateRangeType` | LAST, CURRENT, NEXT, LASTN, NEXTN, TODATE |

#### TOP 필터 (상위/하위 N)

```json
{
  "field": { "fieldCaption": "State/Province" },
  "filterType": "TOP",
  "howMany": 10,
  "fieldToMeasure": { "fieldCaption": "Profit", "function": "SUM" },
  "direction": "TOP"
}
```

#### MATCH 필터 (문자열 패턴)

```json
{
  "field": { "fieldCaption": "State/Province" },
  "filterType": "MATCH",
  "startsWith": "A",
  "contains": "o",
  "endsWith": "a",
  "exclude": false
}
```

#### Context 필터

임의의 필터에 `"context": true`를 추가하면 **Context 필터**로 동작 — 해당 필터를 먼저 적용한 뒤 나머지 필터가 계산된다.

```json
{
  "field": { "fieldCaption": "Category" },
  "filterType": "SET",
  "values": ["Technology"],
  "context": true
}
```

> 한 필드에 필터는 **1개만** 허용된다.

---

### 4.3 테이블 계산(Table Calculations)

테이블 계산은 Tableau가 로컬에서 수행하는 후처리 변환이다. `query.fields` 내 필드에 `tableCalc` 객체를 추가하여 정의한다.

**지원 타입**

| 타입 | 설명 |
|---|---|
| `RANK` | 순위 계산 |
| `PERCENT_OF_TOTAL` | 전체 대비 비율 |
| `RUNNING_TOTAL` | 누적 합계 |
| `DIFFERENCE_FROM` | 이전/다음 값 대비 차이 |
| `PERCENT_DIFFERENCE_FROM` | 이전/다음 값 대비 % 변화 |
| `PERCENT_FROM` | 기준값 대비 비율 |
| `MOVING_CALCULATION` | 이동 평균 |
| `PERCENTILE` | 백분위 |
| `CUSTOM` | 커스텀 수식 |

**예시 ① 지역별 연도별 이익 순위**

```json
{
  "fieldCaption": "Profit",
  "function": "SUM",
  "tableCalc": {
    "tableCalcType": "RANK",
    "dimensions": [
      { "fieldCaption": "Region" },
      { "fieldCaption": "Order Date", "function": "YEAR" }
    ],
    "rankType": "COMPETITION",
    "rankDir": "DESC"
  }
}
```

**예시 ② 3년 이동 평균**

```json
{
  "fieldCaption": "Profit",
  "function": "SUM",
  "tableCalc": {
    "tableCalcType": "MOVING_CALCULATION",
    "dimensions": [ { "fieldCaption": "Order Date", "function": "YEAR" } ],
    "aggregation": "AVG",
    "previous": -2,
    "next": 1,
    "includeCurrent": true
  }
}
```

**예시 ③ 누적 합계 + 2차 계산**

```json
{
  "fieldCaption": "Profit",
  "function": "SUM",
  "tableCalc": {
    "tableCalcType": "RUNNING_TOTAL",
    "dimensions": [ ... ],
    "secondaryTableCalc": {
      "tableCalcType": "PERCENT_DIFFERENCE_FROM",
      "relativeTo": "PREVIOUS"
    }
  }
}
```

> `secondaryTableCalc`는 `RUNNING_TOTAL`과 `MOVING_CALCULATION`에서만 지원된다.

---

### 4.4 파라미터 오버라이드

데이터 소스에 정의된 파라미터 값을 쿼리 시점에 덮어쓸 수 있다.

```json
{
  "query": {
    "fields": [ ... ],
    "parameters": [
      { "parameterCaption": "Profit Bin Size", "value": 50 },
      { "parameterCaption": "Top Customers", "value": 20 }
    ]
  }
}
```

---

### 4.5 응답 옵션(Options)

```json
{
  "options": {
    "debug": true,
    "bypassMetadataCache": false,
    "interpretFieldCaptionsAsFieldNames": false,
    "includeHiddenFields": false,
    "includeGroupFormulas": false,
    "disaggregate": false,
    "returnFormat": "OBJECTS",
    "rowLimit": 1000,
    "returnServerSentEvents": false
  }
}
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `debug` | false | 상세 에러 메시지 활성화 |
| `bypassMetadataCache` | false | 메타데이터 캐시 무시 (소스 변경 후 갱신 필요 시) |
| `interpretFieldCaptionsAsFieldNames` | false | `fieldCaption` 자리에 `fieldName` 사용 허용 |
| `includeHiddenFields` | false | 숨김 필드 포함 |
| `includeGroupFormulas` | false | 그룹 · 빈 상세 정보 포함 |
| `disaggregate` | false | 집계 해제 (행 수준 데이터 반환) |
| `returnFormat` | OBJECTS | `OBJECTS` (가독성) 또는 `ARRAYS` (압축) |
| `rowLimit` | 없음 | 반환 행 수 제한 (정수, ≥1) |
| `returnServerSentEvents` | false | SSE 스트리밍 모드 활성화 (2026.1+) |

---

### 4.6 SSE 스트리밍 (2026.1+)

`returnServerSentEvents: true` 설정 시 결과를 **Server-Sent Events** 방식으로 스트리밍 수신한다. 응답 크기 제한이 없고 대용량 데이터 조회에 적합하다.

**SSE 이벤트 구조**

```json
[
  { "event": "METADATA", "data": { "rowCount": 59 } },
  { "event": "DATA",     "data": [ { "State/Province": "Alabama" }, ... ] },
  { "event": "ERROR",    "data": { "errorCode": "500000", "datetime": "..." } }
]
```

| 이벤트 | 설명 |
|---|---|
| `METADATA` | 예상 행 수 등 메타 정보 |
| `DATA` | 실제 데이터 청크 |
| `ERROR` | 스트리밍 중 발생한 오류 |

---

## 5. 에러 코드

| HTTP | 에러 코드 | 의미 | 주요 원인 |
|---|---|---|---|
| 400 | 400000 | Bad Request | JSON 형식 오류, 잘못된 들여쓰기 |
| 400 | 400800 | 잘못된 계산 수식 | 커스텀 계산 구문 오류 |
| 400 | 400802 | 잘못된 API 요청 | OpenAPI 스펙 미준수 |
| 400 | 400803 | 유효성 검사 실패 | 요청 규칙 위반 |
| 400 | 400804 | 응답 크기 초과 | 필터 추가 필요 (2025.x 이하) |
| 401 | 401001 | 로그인 오류 | 인증 실패 |
| 401 | 401002 | 잘못된 인증 토큰 | 토큰 형식 오류 |
| 403 | 403157 | 기능 비활성화 | 해당 기능 미지원 환경 |
| 403 | 403800 | API Access 권한 없음 | 데이터 소스 권한 설정 필요 |
| 404 | 404934 | 알 수 없는 필드 | fieldCaption 오타 확인 |
| 404 | 404935 | 중복 fieldCaption | 동일 caption 필드 여러 개 존재 |
| 404 | 404950 | 엔드포인트 없음 | URL 오타 |
| 408 | 408000 | 요청 타임아웃 | 쿼리 30분 초과 |
| 429 | 429000 | Too Many Requests | 시간당 쿼리 한도 초과 |
| 500 | 500000 | Internal Server Error | 서버 내부 오류 |
| 500 | 500810 | VDS 빈 테이블 응답 | 데이터 엔진 null 반환 |
| 503 | 503800 | VDS 사용 불가 | 데이터 엔진 접근 불가 |
| 504 | 504000 | Gateway Timeout | 업스트림 응답 지연 |

**에러 처리 패턴**

```python
response = requests.post(url, json=body, headers=headers)

# HTTP 레벨 에러
if response.status_code != 200:
    error = response.json()
    raise Exception(f"[{error['errorCode']}] {error['message']}")

data = response.json()

# 스트리밍 중 발생한 에러 (SSE 모드)
if "error" in data:
    raise Exception(f"Stream error: {data['error']['errorCode']}")
```

---

## 6. 유의사항 및 제한

### 지원하지 않는 계산 유형

| 미지원 항목 | 대안 |
|---|---|
| Python / R 계산 (SCRIPT_REAL 등) | 없음 (Tableau Analytics Extensions 미지원) |
| 공간(Spatial) 계산 | 없음 |
| 패스스루 계산 (RAWSQL) | 없음 |
| 회계 날짜 계산 (Fiscal) | 없음 |
| `COUNT(table)` 함수 | `COUNTD` 등으로 대체 |
| 세트(Set) · 결합 필드(Combined Field) 참조 계산 | 없음 |

### 데이터 소스 제한

- **큐브(Cube) 데이터 소스** 미지원
- 세트(Set) 및 결합 필드는 메타데이터 조회에서도 나타나지 않음

### 필터 제한

- 빈(Bin) · 그룹(Group)을 필터 조건으로 사용 불가
- SET, MATCH, 상대 날짜 필터에 함수 · 계산식 불가
- **한 필드에 필터 1개만** 허용 (예: `SUM(Sales)` 필터를 2개 동시 사용 불가)
- 날짜 시간 집계 (`HOUR`, `MINUTE` 등) 미지원

### 성능 및 용량

| 항목 | 내용 |
|---|---|
| 쿼리 타임아웃 | 30분 초과 시 HTTP 408 반환 |
| 응답 크기 | 2025.x: 1GB 제한 / 2026.1+: 제한 없음 (SSE 스트리밍) |
| 쿼리 속도 제한 | Creator 라이선스 1개당 **시간당 100쿼리** 추가 |

### 인증 관련

- 토큰은 **모든 요청**에 포함 필수 (토큰 만료 주의)
- JWT 사용 시 scope `"tableau:viz_data_service:read"` 필수
- 결과는 요청 사용자의 Tableau 권한에 따라 행 수준 보안(RLS) 적용

### 쿼리 작성 규칙

- `query.fields`에 최소 **1개 이상** 지정 필수
- 동일 필드를 중복 조회하거나 동일 `sortPriority` 부여 불가
- `datasourceLuid` 값에 추가 들여쓰기 · 개행 포함 시 400000 에러 발생

### 트러블슈팅 팁

```http
# 연결 확인용 엔드포인트
GET /api/v1/vizql-data-service/simple-request
```
응답으로 `"ahoy"`가 반환되면 서비스 연결 정상.

- 문제 발생 시 `options.debug: true` 설정으로 상세 에러 확인
- Tableau Server는 서버 로그(`tabadmin` 경로)에서 추가 정보 확인 가능

---

## 7. 버전 히스토리

| 버전 | 출시 | 주요 변경 |
|---|---|---|
| **2026.1** | 2026년 2월 | SSE 스트리밍 결과 반환, 응답 크기 제한 폐지, `rowLimit` 옵션 추가, 그룹·LOD 계산·세트 필터 앨리어스 지원 확대 |
| **2025.3** | 2025년 10월 | 빈/그룹/파라미터 메타데이터 개선, 빈 쿼리 지원, `fieldName` 사용 지원 |
| **2025.2** | 2025년 6월 | 다중 자격증명 지원, Python SDK 출시 |
| **2025.1** | 2025년 2월 | **공개 릴리즈.** 핵심 메소드(read-metadata, read-datasource-model, query-datasource) 제공 |
| Developer Preview | 2024년 6월~10월 | 얼리 액세스 단계 |

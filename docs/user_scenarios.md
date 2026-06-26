# User Scenarios

> Tableau Multi-MCP Agent — 엔드투엔드 유저 시나리오 명세

각 시나리오는 **사용자 발화 → LLM 판단 → MCP 툴 호출 → 가드레일 처리 → 최종 응답** 순서로 기술한다.

---

## 시나리오 A — 공식 Tableau MCP: 대시보드 메타데이터 탐색

### 배경

분석팀 신입 사원이 전사 Tableau 환경에 어떤 대시보드가 있고, 각 뷰가 어떤 데이터 소스를 참조하는지 파악하려 한다.

### 대화 플로우

```
[사용자]
"우리 Tableau 서버에 어떤 워크북이 있어? Sales 관련된 것만 알려줘."

[LLM 판단]
- 의도: 서버 내 워크북 목록 조회 (메타데이터)
- 선택 서버: official_tableau_mcp
- 이유: 워크북 목록은 Tableau Server 객체 계층 정보이며 VDS 데이터 쿼리 대상이 아님

[툴 호출]
official_tableau_mcp → get_workbooks(filter="Sales")

[서버 응답]
{
  "workbooks": [
    { "id": "wb-001", "name": "Sales Dashboard 2025", "project": "영업본부", "views": 4 },
    { "id": "wb-002", "name": "Sales Pipeline KPI",   "project": "영업본부", "views": 7 }
  ]
}

[에이전트 답변]
"현재 Tableau 서버의 영업본부 프로젝트에 Sales 관련 워크북 2개가 있습니다.
 1. Sales Dashboard 2025 — 뷰 4개
 2. Sales Pipeline KPI — 뷰 7개
 특정 워크북의 뷰 상세나 데이터 소스 연결 정보가 필요하시면 알려주세요."
```

### 후속 탐색 플로우

```
[사용자]
"Sales Dashboard 2025 안에 어떤 뷰가 있어? 담당자가 누군지도 알고 싶어."

[LLM 판단]
- 의도: 특정 워크북 내 뷰 목록 + 소유자 정보 (서버 메타데이터)
- 선택 서버: official_tableau_mcp (연속 메타데이터 조회)

[툴 호출 — 병렬]
official_tableau_mcp → get_views(workbook_id="wb-001")
official_tableau_mcp → get_workbook_owner(workbook_id="wb-001")

[에이전트 답변]
"Sales Dashboard 2025 워크북 정보:
 담당자: 김민준 (minjun.kim@company.com)
 포함된 뷰:
   - 월별 매출 추이
   - 지역별 파이프라인 현황
   - 제품군별 목표 달성률
   - 영업사원 리더보드"
```

---

## 시나리오 B — ta_mcp: VDS 데이터 쿼리 + 가드레일 작동

### 배경

영업 관리자가 특정 분기 지역별 매출 합계를 자연어로 요청한다. 이 시나리오는 Pre-hook 검증 실패 → 자동 복구 → Post-hook 검증 → 최종 정합성 보정 루프 전체를 포함한다.

### 정상 플로우

```
[사용자]
"2025년 3분기 지역별 Sales 합계 알려줘."

[LLM 판단]
- 의도: 수치 집계 쿼리 (데이터 레이어)
- 선택 서버: ta_mcp
- 실행 순서: list_vds_sources → query_vds_data

─────────────────────────────────────────
 STEP 1. 데이터 소스 목록 조회
─────────────────────────────────────────
[툴 호출]
ta_mcp → list_vds_sources()

[ta_mcp 응답]
[
  { "id": "ds-sales-001", "name": "Sales_Master",    "description": "전사 매출 원천 데이터" },
  { "id": "ds-hr-002",    "name": "HR_Headcount",    "description": "인사 현황" },
  { "id": "ds-mktg-003",  "name": "Marketing_Leads", "description": "마케팅 리드 데이터" }
]

─────────────────────────────────────────
 STEP 2. VDS 쿼리 실행 (Pre-hook 검증)
─────────────────────────────────────────
[LLM → 툴 호출 준비]
ta_mcp → query_vds_data(
  source_id = "ds-sales-001",
  fields    = ["Region", "Sales"],
  filters   = [
    { "field": "Quarter", "value": "Q3-2025" }
  ]
)

[Pre-hook 가드레일 실행]
✅ source_id 존재 여부: "ds-sales-001" → 확인됨
✅ fields 필수값: ["Region", "Sales"] → 비어있지 않음
→ VDS API 호출 진행

[VDS API 응답]
{
  "data": [
    { "Region": "수도권", "Sales": 1_850_000_000 },
    { "Region": "부산/경남", "Sales": 720_000_000 },
    { "Region": "대구/경북", "Sales": 430_000_000 },
    { "Region": "기타",     "Sales": 210_000_000 }
  ]
}

[Post-hook 가드레일 실행]
✅ 응답 내 'data' 키 존재: 확인됨
→ 정합성 통과

[에이전트 최종 답변]
"2025년 3분기 지역별 Sales 합계입니다.

 | 지역      | 매출         |
 |-----------|-------------|
 | 수도권    | 18억 5천만 원 |
 | 부산/경남 | 7억 2천만 원  |
 | 대구/경북 | 4억 3천만 원  |
 | 기타      | 2억 1천만 원  |
 | **합계**  | **32억 1천만 원** |"
```

### 비정상 플로우 — Pre-hook 실패 및 자동 복구

```
[사용자]
"3분기 Sales 요약해줘." (fields 정보 불명확)

[LLM → 툴 호출 준비 — 잘못된 인자]
ta_mcp → query_vds_data(
  source_id = "ds-sales-001",
  fields    = [],              ← 빈 리스트
  filters   = []
)

─────────────────────────────────────────
 Pre-hook 가드레일 개입
─────────────────────────────────────────
❌ fields 필수값 검증 실패
   ValueError: 필수 인자 누락: 'fields'
→ VDS API 호출 차단

[MCP 오류 응답 → LLM 수신]
"tool_error: 필수 인자 누락: 'fields'"

[LLM 자율 복구 판단]
- 사용자 의도에서 'Sales' 수치가 핵심임을 재추론
- 기본 집계 필드 ["Region", "Sales", "Quantity"] 를 자체 추정하여 재호출

[재호출]
ta_mcp → query_vds_data(
  source_id = "ds-sales-001",
  fields    = ["Region", "Sales", "Quantity"],
  filters   = [{ "field": "Quarter", "value": "Q3-2025" }]
)

[Pre-hook 재검증]
✅ fields 비어있지 않음 → 통과
→ 정상 VDS 응답 수신 후 최종 답변 생성
```

### 비정상 플로우 — Post-hook 실패 및 사용자 알림

```
[VDS API 응답 — 비정상]
{ "status": "ok", "result": [...] }   ← 'data' 키 누락

─────────────────────────────────────────
 Post-hook 가드레일 개입
─────────────────────────────────────────
❌ 응답 내 'data' 키 없음
   RuntimeError: VDS 응답에 'data' 키가 없습니다.

[LLM 사용자 알림]
"데이터를 가져왔으나 응답 구조가 예상과 달라 수치를 정확히 파싱할 수 없었습니다.
 Tableau VDS API 응답 형식이 변경되었을 수 있습니다.
 관리자에게 확인을 요청하거나, 조회 필드 조건을 변경해서 다시 시도해 주세요."
```

---

## 가드레일 요약

| 단계 | 검증 항목 | 실패 시 동작 |
|---|---|---|
| Pre-hook | `source_id` 비어있지 않음 | `ValueError` → VDS 호출 차단, LLM 재시도 |
| Pre-hook | `fields` 비어있지 않음 | `ValueError` → VDS 호출 차단, LLM 재시도 |
| Post-hook | 응답에 `'data'` 키 존재 | `RuntimeError` → 사용자에게 구조 오류 알림 |

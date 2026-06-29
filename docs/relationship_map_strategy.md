# 데이터소스 관계 맵 전략

## 배경

Tableau VDS는 **단일 퍼블리시 데이터소스**만 쿼리 가능하다.
사용자가 여러 소스에 걸친 데이터를 요청할 경우 (예: "비용센터별 매출 + 인원수"),
두 소스를 각각 쿼리한 뒤 Python에서 조인해야 하는데,
현재 메타데이터에는 **소스 간 조인 키 정보가 없다.**

관계 맵은 이 문제를 해결하기 위해 구축하는 레이어다.

---

## 전략 개요: 반자동 3단계

```
[자동] 동일 fieldName 크로스 매칭
          ↓
[자동] LLM이 관계 후보 추론
          ↓
[사용자] Monitor UI에서 Accept / Reject만
```

직접 전부 입력하는 방식은 78개 소스 기준 수백 개 관계를 타이핑해야 하므로 비현실적이다.
자동 탐지 + LLM 추론으로 후보를 생성하고 사용자는 확인만 한다.

---

## 1단계 — 자동: 동일 fieldName 크로스 매칭

이미 수집된 `app_log.json`의 필드 데이터에서
**동일한 `fieldName`이 2개 이상 소스에 존재하면 조인 키 후보로 자동 추출한다.**

추가 입력 없이 코드로 도출 가능하다.

### 실제 데이터 예시

```
COMPANY_CODE   → LGC_CCTR(변환), LGC_MATERIAL(변환), LGC_SALES ...
TENANT_ID      → LGC_CCTR(변환), LGC_HR ...
CCTR_CODE      → LGC_CCTR(변환), LGC_BUDGET ...
```

---

## 2단계 — 자동: LLM 관계 추론

같은 Project 내 소스들의 필드 목록을 LLM에 제공하고 관계를 추론하게 한다.

### LLM 입출력 예시

**입력:**
```
소스: LGC_CCTR (필드: CCTR_CODE, COMPANY_CODE, CCTR_NAME ...)
소스: LGC_BUDGET (필드: CCTR_CODE, COMPANY_CODE, AMOUNT ...)
```

**출력:**
```json
{
  "from": "LGC_BUDGET",
  "to": "LGC_CCTR(변환)",
  "join_keys": [
    { "from_field": "CCTR_CODE", "to_field": "CCTR_CODE" }
  ],
  "confidence": "high",
  "reason": "동일한 CCTR_CODE 필드가 양측에 존재, 비용센터-예산 관계로 추정"
}
```

---

## 3단계 — 사용자: Monitor UI에서 확인

자동 생성된 후보를 Monitor HTML에 표시하고 사용자는 클릭으로만 확정한다.

```
┌─────────────────────────────────────────────────────┐
│  관계 후보 (자동 탐지) — 15건                        │
├──────────────┬──────────────────┬────────┬──────────┤
│ FROM         │ TO               │ 키     │ 신뢰도   │
├──────────────┼──────────────────┼────────┼──────────┤
│ LGC_BUDGET   │ LGC_CCTR(변환)   │CCTR_CODE│ HIGH   │
│ [✓ Accept]   │ [✗ Reject]       │        │          │
├──────────────┼──────────────────┼────────┼──────────┤
│ LGC_SALES    │ LGC_CCTR(변환)   │CCTR_CODE│ HIGH   │
│ [✓ Accept]   │ [✗ Reject]       │        │          │
└──────────────┴──────────────────┴────────┴──────────┘
```

Accept 클릭 → `app_log.json`의 `relationships[]`에 저장.

---

## 사용자 직접 입력이 필요한 경우

자동 탐지는 **필드명이 동일한 경우**만 잡는다.
**이름이 달라도 같은 개념인 의미적 관계**는 수동 보완이 필요하다.

```
예: LGC_SALES의 "부서코드" ↔ LGC_CCTR의 "CCTR_CODE"
    → 이름이 달라서 자동 탐지 불가 → 수동 추가
```

이런 케이스는 전체의 10~20% 수준으로, 부담이 크지 않다.

---

## 역할 분담 요약

| 작업 | 담당 | 사용자 부담 |
|---|---|---|
| 동일 필드명 조인 후보 추출 | 자동 (코드) | 없음 |
| 관계 의미 추론 | LLM | 없음 |
| 후보 Accept / Reject | 사용자 | 클릭만 |
| 이름 다른 의미적 관계 | 사용자 | 소수만 직접 입력 |

---

## 구현 계획

1. `fetch_step01.py`에 크로스 매칭 로직 추가
   - 전체 소스의 `fieldName` 역인덱스 생성
   - 2개 이상 소스에 등장하는 필드명 → `relationship_candidates[]`로 저장
2. LLM 추론 스크립트 (`fetch_step01_relations.py`) 추가
   - Project별로 소스 그룹핑 후 LLM에 추론 요청
   - 결과를 `relationship_candidates[]`에 병합
3. `monitor.html` STEP 01 패널에 관계 후보 확인 UI 추가
   - Accept → `relationships[]`로 이동
   - Reject → 후보 목록에서 제거
4. `app_log.json` 스키마 확장
   ```json
   {
     "step01": {
       "relationship_candidates": [],
       "relationships": []
     }
   }
   ```

---

## 관련 파일

| 파일 | 역할 |
|---|---|
| `src/fetch_step01.py` | 메타데이터 수집 + 크로스 매칭 로직 추가 예정 |
| `src/app_log.json` | 관계 후보 및 확정 관계 저장 |
| `src/monitor.html` | 관계 후보 확인 UI 추가 예정 |
| `docs/relationship_map_strategy.md` | 이 문서 |

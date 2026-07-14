# Architecture Plan

> Tableau Multi-MCP Agent — 시스템 아키텍처 설계 및 단계별 개발 로드맵

---

## 1. 시스템 개요

이 시스템은 단일 LLM 에이전트가 두 개의 MCP 서버를 동시에 운영하여 Tableau 환경의 **메타데이터 조회**와 **데이터 수치 쿼리**를 책임 영역별로 분리 처리하는 구조다. 나아가 도출된 수치의 BI 정합성을 N차 보정 루프로 검증하고, 업무 단위별 서브 에이전트가 협력하여 종합 리포트를 자동 생성하는 멀티 에이전트 오케스트레이션으로 확장된다.

### 핵심 설계 원칙

- **서버 분리**: 공식 MCP(서버 정보)와 ta_mcp(데이터)는 독립 프로세스로 분리되어 장애가 상호 전파되지 않는다.
- **LLM 기반 라우팅**: rule-based 라우터 없이 Claude의 툴 선택 판단에 시스템 프롬프트 가이드를 제공한다.
- **가드레일 내재화**: 데이터 쿼리 경로(ta_mcp)에만 Pre/Post-hook 검증을 적용하여 BI 정합성을 보장한다.
- **N차 보정 루프**: VDS 결과와 Tableau View 실제 수치를 백엔드에서 대조하여 오차 발생 시 추출 인자를 자동 재보정한다.
- **레시피 관리**: 검증 완료된 최적 추출 인자 조합을 재사용 가능한 레시피(Recipe)로 저장·관리한다.

---

## 2. 멀티 MCP 라우팅 메커니즘

### 라우팅 분기 조건

| 질문 유형 | 선택 서버 | 판단 근거 |
|---|---|---|
| 워크북·대시보드·뷰·시트 구조 탐색 | `official_tableau_mcp` | Tableau Server 객체 계층 조회 |
| 사용자·퍼미션·프로젝트 정보 | `official_tableau_mcp` | 서버 관리 메타데이터 |
| 데이터 원본(VDS) 목록 확인 | `ta_mcp` → `list_vds_sources` | 분석 전 소스 선택 단계 |
| 수치·지표 집계·분석 | `ta_mcp` → `query_vds_data` | VDS REST 쿼리 실행 |

### 라우팅 판단 흐름 (N차 보정 루프 포함)

```
사용자 질문 입력
       │
       ▼
[가이드라인 & 프로파일링 레이어]
  - 업무 담당자 가이드라인 → 시스템 프롬프트 바인딩
  - VDS 메타데이터 자동 프로파일링 (도메인·최소/최대값·글로서리)
       │
       ▼
Claude (LLM) — 시스템 프롬프트 + 툴 description 분석
       │
       ├─ [메타데이터 의도] ──→ official_tableau_mcp 툴 선택
       │                         (워크북, 대시보드, 사용자 등)
       │
       └─ [데이터 조회 의도] ──→ ta_mcp 툴 선택
                                  ├─ list_vds_sources (소스 목록)
                                  └─ query_vds_data (수치 쿼리)
                                         │
                                    [Pre-hook 가드레일]
                                    source_id 존재 여부
                                    fields 필수값 검증
                                         │
                                    VDS API 호출
                                         │
                                    [Post-hook 가드레일]
                                    응답 'data' 키 검증
                                         │
                                ┌────────▼────────┐
                                │  N차 보정 루프   │
                                │                 │
                                │ VDS 결과값      │
                                │    ↕ 대조       │
                                │ Tableau View    │
                                │ 실제 수치       │
                                │                 │
                                │ 오차 발생?      │
                                │  ├─ YES → 추출  │
                                │  │    인자 재보정│
                                │  │    (N차 재시도│
                                │  │    최대 3회) │
                                │  └─ NO  → 통과  │
                                └────────┬────────┘
                                         │ 검증 완료
                                ┌────────▼────────┐
                                │  레시피 저장     │
                                │  (최적 추출      │
                                │   인자 조합)     │
                                └────────┬────────┘
                                         │
                                    최종 답변 생성
```

---

## 3. ASCII 아키텍처 맵

```
┌──────────────────────────────────────────────────────────────────────┐
│                         사용자 인터페이스                              │
│                     (CLI stdin / 향후 Web UI)                         │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ 자연어 질문 + 분석 가이드라인
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│              가이드라인 & 자동 프로파일링 레이어                        │
│                                                                      │
│  ┌──────────────────────────┐   ┌──────────────────────────────────┐ │
│  │  업무 담당자 가이드라인    │   │  VDS 메타데이터 자동 프로파일러   │ │
│  │  (자유 구술형 텍스트 입력) │   │                                  │ │
│  │  ↓                       │   │  • 필드 도메인 분석               │ │
│  │  시스템 프롬프트 바인딩    │   │  • 최소/최대값 범위 추출          │ │
│  │  컨텍스트 주입            │   │  • 동의어 글로서리 자동 생성       │ │
│  └──────────────────────────┘   └──────────────────────────────────┘ │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ 강화된 시스템 프롬프트 + 필드 컨텍스트
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        main_agent.py                                 │
│                                                                      │
│   ┌─────────────────┐           ┌──────────────────────────────┐    │
│   │  TableauAgent   │           │       MultiMCPClient          │    │
│   │                 │◄─────────►│                              │    │
│   │  Anthropic LLM  │           │  tool_owner 인덱스            │    │
│   │  agentic loop   │           │  세션 디스패처                │    │
│   └─────────────────┘           └──────────────┬───────────────┘    │
│                                                │                    │
└────────────────────────────────────────────────┼────────────────────┘
                              ┌───────────────────┴───────────────────┐
                              │                                       │
                stdio (subprocess)                      stdio (subprocess)
                              │                                       │
            ┌─────────────────▼──────┐           ┌────────────────────▼──────┐
            │   official_tableau_mcp  │           │          ta_mcp            │
            │                        │           │     (tableau_mcp.py)        │
            │ • get_workbooks         │           │                            │
            │ • get_views             │           │ • list_vds_sources          │
            │ • get_users             │           │ • query_vds_data            │
            │ • get_dashboards        │           │     ├ Pre-hook 검증         │
            └──────────┬─────────────┘           │     ├ VDS API 호출          │
                       │                         │     ├ Post-hook 검증        │
            ┌──────────▼──────────┐              │     └ N차 보정 루프         │
            │  Tableau Server /   │              │         ↕ View 수치 대조    │
            │  Tableau Cloud      │              │         재보정 → 레시피 저장 │
            │  REST API           │              └──────────────┬──────────────┘
            └─────────────────────┘                            │
                                               ┌──────────────▼──────────────┐
                                               │        config.py             │
                                               │     TableauVDSConnector      │
                                               │     (PAT 인증 + httpx)       │
                                               └──────────────┬──────────────┘
                                                              │
                                               ┌──────────────▼──────────────┐
                                               │      Tableau VDS API         │
                                               │   (VizQL Data Service)       │
                                               └──────────────────────────────┘
```

---

## 4. STEP 01 — 메타데이터 수집 파이프라인 및 모니터링

멀티 MCP 에이전트 런타임과 별도로, **오프라인 데이터 수집/프로파일링 파이프라인**을 구축했다. 에이전트가 참조할 KPI·데이터소스·필드 메타데이터를 사전에 SQLite에 적재하고, 파이프라인 진행 상황과 인프라 상태를 대시보드로 모니터링한다.

| 파일 | 역할 |
|---|---|
| `src/fetch_step01.py` | STEP 01 실행 스크립트. VDS REST API(`read-metadata`, `query-datasource`)로 데이터소스·필드 메타데이터 및 필드별 기술 통계(결측·고유값·최소/최대/평균·상위값)를 수집해 `metadata.db`에 적재하고, 이어서 **Gemini API**로 필드 비즈니스 글로서리를 자동 생성한 뒤 `app_log.json` 스냅샷을 생성한다. |
| `src/db.py` | SQLite 저장소. `datasources` / `fields` / `field_synonyms` / `kpis` / `kpi_datasources` / `kpi_glossary` / `field_business_glossary` / `field_stats` / `datasource_relationships` 스키마와 `build_step01_snapshot()`(KPI→데이터소스→필드 트리 조립) 제공. |
| `src/health_check.py` | VDS API·ta_mcp·공식 Tableau MCP 인프라 상태를 병렬 점검하고 STEP 01 스냅샷을 `app_log.json`에 병합. `--watch`(주기 점검), `--serve`(정적 서버 기동) 옵션 제공. |
| `src/monitor.html` | `app_log.json` 기반 STEP 01~05 파이프라인 모니터링 대시보드(정적 페이지). STEP 01은 실데이터, STEP 02~05는 Phase 2/3 구현 전까지 목업으로 표시. |

```
uv run python src/fetch_step01.py        # metadata.db + app_log.json 생성 (필드 통계 + Gemini 글로서리 포함)
uv run python src/health_check.py --serve  # 헬스체크 + http://localhost:8000/monitor.html
```

이 파이프라인은 향후 Phase 2의 `MetadataProfiler`(자동 프로파일링) 및 `RecipeStore`(레시피 관리)의 데이터 기반이 되며, `kpi_glossary`/`field_synonyms` 테이블은 업무 담당자 가이드라인 바인딩과 연결될 예정이다.

### 4-1. 필드 비즈니스 글로서리 자동 생성 (LLM: Gemini)

KPI 미배정 상태에서도 필드 자체의 비즈니스 의미를 확보하기 위해, `kpi_glossary`(KPI-필드 종속)와 별개로 `field_business_glossary`(필드 단독) 테이블을 두고 LLM이 자동 채운다.

| 항목 | 내용 |
|---|---|
| 호출 시점 | STEP 01의 필드 메타데이터·기술통계 수집 직후, 배치·오프라인 1회성 실행 (실시간 에이전트 런타임과 분리) |
| 사용 모델 | Gemini (`google-genai` SDK), 모델 ID는 `GEMINI_MODEL` 환경변수 (기본값 `gemini-3.5-flash`) |
| 페르소나 | "병원 경영 분석 스키마 전문 비즈니스 분석가" 시스템 인스트럭션 |
| 입력 컨텍스트 | 필드 원본명·타입·역할·기본 집계 + VDS 통계(결측/고유값/최소/최대/평균) + (선택) `src/guideline.txt` 업무 가이드라인 |
| 구조화된 출력 | Pydantic `GlossaryItem`(`field_name`/`logical_name`/`description`/`analysis_usage`) 리스트를 `response_schema`로 강제, 파싱 실패 시 원문 JSON 재파싱 폴백 |
| 토큰 최적화 | `get_fields_missing_glossary()`로 미생성 필드만 선별 호출, `is_confirmed=1`(현업 승인) 필드는 재생성 대상에서 제외 |
| 장애 격리 | `GEMINI_API_KEY` 미설정 또는 API 오류 시 해당 필드만 스킵, STEP 01 나머지 파이프라인은 정상 진행 |

---

## 5. 단계별 개발 로드맵

### Phase 1 — 기반 구축 (완료)

**목표**: 로컬 환경에서 두 MCP 서버가 연결되고, 단순 질문에 정확한 서버로 라우팅되는 것을 검증한다.

| 항목 | 내용 |
|---|---|
| 완료 기준 | `main_agent.py` 실행 후 메타 질문 → 공식 MCP, 수치 질문 → ta_mcp 정상 응답 |
| 핵심 구현 | `config.py`, `tableau_mcp.py`(ta_mcp), `main_agent.py` |
| 가드레일 | Pre-hook: 필수 인자 검증 / Post-hook: 응답 키 검증 |
| 이력서 키워드 | `MCP`, `LLM Tool Use`, `Anthropic API`, `Tableau VDS API`, `async Python` |
| STEP 01 확장 | `fetch_step01.py`/`db.py`로 KPI·필드 메타데이터 수집 및 SQLite 저장소 구축 완료, `health_check.py`/`monitor.html`로 파이프라인 모니터링 체계 구축 완료 |
| STEP 01 글로서리 확장 | `field_business_glossary` 스키마 및 Gemini 기반 자동 생성 파이프라인 구축 완료 (구조화된 출력, 토큰 최적화, 가이드라인 주입 포함) |

### Phase 2 — 정합성 보정 루프 및 레시피 관리

**목표**: VDS 결과와 Tableau View 실제 수치를 자동 대조하여 오차 발생 시 추출 인자를 N차 재보정하고, 검증된 조합을 레시피로 저장·재사용한다. 메타데이터 자동 프로파일링 레이어와 업무 담당자 가이드라인 바인딩을 구현한다.

| 항목 | 내용 |
|---|---|
| 완료 기준 | 오차 임계값(±1%) 초과 시 자동 재보정 3회 이내 수렴, 레시피 파일 저장 및 재호출 성공 |
| 핵심 구현 | `RecipeStore`(레시피 저장소), `ValidationLoop`(N차 보정), `MetadataProfiler`(자동 프로파일링), 가이드라인 → 시스템 프롬프트 바인더 |
| 가드레일 확장 | 보정 횟수 초과 시 담당자 알림 및 수동 검토 플래그 발행 |
| 이력서 키워드 | `Data Validation Loop`, `BI Accuracy`, `Metadata Profiling`, `Recipe Management`, `Agentic Self-Correction` |

### Phase 3 — 멀티 서브 에이전트 오케스트레이션 및 리포트 자동화

**목표**: 업무 단위별 서브 에이전트가 병렬로 지표를 추출·검증하고, 모닝 브리핑 에이전트가 Jinja2 템플릿으로 종합 리포트를 조합하여 자동 배포한다.

```
[멀티 에이전트 구조]

오케스트레이터 (main_agent.py)
       │
       ├─ 수익 지표 서브 에이전트 ──→ VDS 가이드라인 참조 → 단위 리포트(.md) 생성
       ├─ 병상 가동률 서브 에이전트 → VDS 가이드라인 참조 → 단위 리포트(.md) 생성
       ├─ 외래 현황 서브 에이전트 ──→ VDS 가이드라인 참조 → 단위 리포트(.md) 생성
       └─ (업무 단위별 확장 가능)
                    │ 단위 리포트 수집
                    ▼
       모닝 브리핑 에이전트
                    │
                    ▼
       Jinja2 템플릿 엔진
       (가변형 다차원 리포트 렌더링)
                    │
                    ▼
       종합 리포트 (.md / HTML / PDF)
       → Slack / Email / Web 배포
```

| 항목 | 내용 |
|---|---|
| 완료 기준 | 서브 에이전트 3종 병렬 실행, 모닝 브리핑 리포트 자동 생성 및 Slack 전송 성공 |
| 핵심 구현 | `SubAgent` 베이스 클래스, `BriefingOrchestrator`, Jinja2 리포트 템플릿, 배포 커넥터 |
| 이력서 키워드 | `Multi-Agent Orchestration`, `Parallel Async Agents`, `Jinja2 Report Engine`, `Automated Briefing`, `Production LLM System` |

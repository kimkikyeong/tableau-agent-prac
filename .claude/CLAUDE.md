# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tableau Agent — an AI agent project that interacts with Tableau (Server/Cloud) using Python.

## Environment

- **Python**: 3.14.6 (managed via `uv`)
- **Virtual environment**: `.venv/` (created with `uv venv`)

## Common Commands

```powershell
# Activate virtual environment
.venv\Scripts\activate

# Install a package
uv add <package>

# Install dev dependency
uv add --dev <package>

# Run a script
uv run python <script.py>

# Sync dependencies
uv sync
```

## Package Management

`uv`로 의존성을 관리한다. `pip install` 직접 사용 금지 — `uv add`로만 추가하여 `pyproject.toml` / `uv.lock` 동기화를 유지한다. `uv.lock`은 재현 가능한 빌드를 위해 반드시 커밋한다.

## Project Architecture

- **목적:** Tableau Server/Cloud를 AI Agent로 제어 (MCP / VDS 프로토콜 활용)
- **핵심 기술스택:** Python 3.14, uv, httpx (비동기 HTTP), python-dotenv, mcp, anthropic

### 주요 모듈 구조

| 파일 | 역할 |
|---|---|
| `src/config.py` | `TableauConfig`(환경변수 로드) + `TableauVDSConnector`(PAT 인증·세션 관리, async context manager) |
| `src/tableau_mcp.py` | **ta_mcp** FastMCP 서버 (독립 프로세스). MCP 툴 3개 제공. `uv run python src/tableau_mcp.py` |
| `src/main_agent.py` | 메인 에이전트. `MultiMCPClient`(다중 MCP 세션) + `TableauAgent`(Claude agentic loop). `uv run python src/main_agent.py` |
| `src/test_connections.py` | REST API / VDS 엔드포인트 연결 통합 테스트. `uv run python src/test_connections.py` |

### VDS 엔드포인트 (공식 스펙 준수)

| 기능 | 메서드 | 경로 |
|---|---|---|
| 데이터 소스 목록 | GET | `/api/{version}/sites/{site_luid}/datasources` |
| 필드 메타데이터 | POST | `/api/v1/vizql-data-service/read-metadata` |
| 데이터 쿼리 | POST | `/api/v1/vizql-data-service/query-datasource` |

### `TableauVDSConnector` 퍼블릭 메서드

| 메서드 | 설명 |
|---|---|
| `get_datasource_metadata()` | REST API로 사이트 내 전체 데이터 소스 목록 반환 |
| `get_vds_metadata(datasource_luid)` | VDS read-metadata: 필드·파라미터 스키마 반환 |
| `query(source_id, query_payload, options)` | VDS query-datasource: 실제 데이터 쿼리 실행 |

### VDS 쿼리 요청 형식

```json
{
  "datasource": { "datasourceLuid": "<LUID>" },
  "query": {
    "fields": [
      { "fieldCaption": "Category" },
      { "fieldCaption": "Sales", "function": "SUM" }
    ],
    "filters": [
      { "filterType": "SET", "field": { "fieldCaption": "Region" },
        "values": ["East"], "exclude": false }
    ]
  },
  "options": { "rowLimit": 1000 }
}
```

### MCP 역할 분리 원칙

| 단계 | 서버 | 툴 | 역할 |
|---|---|---|---|
| 1단계 | 공식 Tableau MCP | `list-datasources`, `search-content` | LUID 획득 |
| 2단계 | 공식 Tableau MCP | `get-datasource-metadata` | 필드 스키마 획득 (VDS + Metadata API 통합) |
| 3단계 | ta_mcp | `query_vds_data` | 실제 데이터 쿼리 실행 |

공식 MCP는 탐색·컨텍스트 수집 전담, ta_mcp는 VDS 쿼리 실행 전담. 역할 중복 없음.

### ta_mcp 툴 (커스텀 VDS 서버 — `src/tableau_mcp.py`)

| 툴 | 설명 |
|---|---|
| `query_vds_data(source_id, fields, aggregations, filters)` | VDS 쿼리 실행. source_id·fields는 공식 MCP에서 획득한 값을 전달. 내부에서 VDS 형식으로 자동 변환. |

### MCP 구성 (Multi-Server)

- `official_tableau_mcp`: 공식 Tableau MCP 서버. LUID 조회·필드 스키마·워크북·뷰 등 탐색 전담. 명령어는 `TABLEAU_OFFICIAL_MCP_CMD` / `TABLEAU_OFFICIAL_MCP_ARGS` 환경 변수로 지정.
- `ta_mcp`: 커스텀 VDS 서버 (`src/tableau_mcp.py`). VDS 데이터 쿼리 실행 전담.

### 라우팅 방식
LLM(Claude)이 시스템 프롬프트의 3단계 흐름 지시를 따라 순서대로 툴을 호출. 수치 조회는 반드시 공식 MCP(1·2단계) → ta_mcp(3단계) 순서.

### 인증
PAT(Personal Access Token). VDS 세션은 `async with TableauVDSConnector()` 블록 안에서만 유효. PAT는 15일 미사용 시 자동 만료.

### 환경 변수
`.env.example` 참고. 필수: `TABLEAU_VDS_ENDPOINT`, `TABLEAU_PAT_NAME`, `TABLEAU_PAT_SECRET`, `TABLEAU_OFFICIAL_MCP_CMD`, `ANTHROPIC_API_KEY`

---

# Claude Development Guidelines for Tableau MCP / VDS Agent Project

이 문서는 본 프로젝트를 진행하는 동안 Claude가 반드시 준수해야 하는 최우선 지침(Strict Guidelines)이다. 모든 답변과 코드 생성은 아래 원칙을 위배해서는 안 된다.

---

## 1. 언어 및 커뮤니케이션 원칙
- **한국어 사용:** 모든 설명, 주석, 답변은 명확하고 전문적인 한국어로 작성한다. 단, 코드 내 변수명, 함수명, 시스템 아키텍처 용어는 글로벌 표준 영문 표기법을 따른다.

## 2. 코드 작성 및 최적화 원칙
- **재사용성 극대화:** 코드는 모듈화되어야 하며, 향후 확장 및 재사용이 가능하도록 인터페이스와 클래스, 함수 구조를 설계한다.
- **Dead Code 제거:** 현재 구현 단계에서 사용하지 않는 불필요한 코드, 임시 테스트용 코드, 중복 라이브러리 호출 등은 코드를 출력하기 전에 스스로 철저히 점검하여 반드시 삭제 후 청결한 코드만 제공한다.

## 3. 코드 수정 및 유지보수 원칙
- **최소 코드 영향도 (Targeted Modification):** 사용자가 코드 수정을 요청한 경우, **요청 사항과 직접적으로 연계된 부분만 정밀하게 수정**한다.
- **기존 코드 보존:** 수정 범위를 벗어난 나머지 정상 작동 코드는 절대로 임의로 변경하거나 생략(`// 기존 코드 생략...` 등 포함)하지 않고 원본의 정합성을 유지한다.

## 4. 최종 검증 및 자가 검토 (Self-Review)
- **적용 범위:** 신규 모듈 작성 또는 로직 변경이 수반되는 수정에 한해 수행한다. 단순 오타 수정, 주석 변경, 포맷팅 수정은 생략한다.
- **출력 형식:** 답변 마지막에 아래 포맷을 **한 번만** 간결하게 출력한다. 각 항목은 1~2문장 이내로 작성한다.

### [Self-Review Result]
1. **요청사항 반영 여부:** (누락된 요구사항 유무)
2. **코드 클린업 점검:** (불필요한 코드 잔존 여부)
3. **영향도 체크:** (수정 범위 외 기존 로직 변경 여부)

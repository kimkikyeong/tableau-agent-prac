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

> 아키텍처가 확정되면 이 섹션을 업데이트한다. Claude는 코드 탐색 전 이 섹션을 먼저 참고해 불필요한 파일 탐색을 최소화한다.

- **목적:** Tableau Server/Cloud를 AI Agent로 제어 (MCP / VDS 프로토콜 활용)
- **핵심 기술스택:** Python 3.14, uv, httpx (비동기 HTTP), python-dotenv, mcp, anthropic
- **주요 모듈 구조:**
  - `src/config.py` — `TableauConfig`(환경변수 로드) + `TableauVDSConnector`(PAT 인증·세션·쿼리 베이스, async context manager)
  - `src/tableau_mcp.py` — **ta_mcp** FastMCP 서버 (독립 프로세스). `list_vds_sources`, `query_vds_data` 툴 제공. `uv run python src/tableau_mcp.py`로 기동.
  - `src/main_agent.py` — 메인 에이전트 진입점. `MultiMCPClient`(다중 서버 세션 관리) + `TableauAgent`(Claude 기반 agentic loop). `uv run python src/main_agent.py`로 실행.
- **MCP 구성 (Multi-Server):**
  - `official_tableau_mcp`: 공식 Tableau MCP 서버 (대시보드·메타데이터 조회). 명령어는 `TABLEAU_OFFICIAL_MCP_CMD` / `TABLEAU_OFFICIAL_MCP_ARGS` 환경 변수로 지정.
  - `ta_mcp`: 커스텀 VDS 서버 (`src/tableau_mcp.py`). 실제 데이터 수치·지표 쿼리 담당.
- **라우팅 방식:** LLM(Claude)이 시스템 프롬프트 가이드 + 툴 description을 기반으로 자동 판단. 별도 rule-based 라우터 없음.
- **인증:** PAT(Personal Access Token). VDS 세션은 `async with TableauVDSConnector()` 블록 안에서만 유효.
- **환경 변수:** `.env.example` 참고. 필수: `TABLEAU_VDS_ENDPOINT`, `TABLEAU_PAT_NAME`, `TABLEAU_PAT_SECRET`, `TABLEAU_OFFICIAL_MCP_CMD`, `ANTHROPIC_API_KEY`

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

# Tableau Multi-MCP Agent

> 자연어 질문을 Tableau 데이터 지표로 변환하는 AI 에이전트 — BI 정합성과 가드레일을 갖춘 멀티 MCP 아키텍처

---

## Why This Project

Tableau 환경에서 LLM 기반 데이터 조회는 두 가지 핵심 문제를 갖는다.

1. **BI 정합성 부재** — LLM이 직접 데이터를 가공하면 집계 기준·필터 조건 오류가 검출 불가능한 채로 최종 답변에 반영된다.
2. **툴 난립** — 메타데이터 조회(워크북·대시보드 구조)와 실제 수치 쿼리(VDS API)가 동일 경로로 라우팅되면 책임 경계가 모호해진다.

이 프로젝트는 **공식 Tableau MCP(메타데이터 레이어)**와 **커스텀 ta_mcp(VDS 데이터 레이어)**를 분리 등록하고, LLM이 질문 의도에 따라 자동으로 올바른 서버를 선택하도록 설계한다.

---

## Tech Stack

| 영역 | 기술 | 역할 |
|---|---|---|
| LLM | Claude (Anthropic API) | 의도 파악 및 툴 라우팅 |
| MCP 프로토콜 | `mcp` Python SDK | 다중 서버 세션 관리 |
| Tableau 메타데이터 | 공식 Tableau MCP 서버 | 워크북·대시보드·사용자 정보 |
| Tableau 데이터 쿼리 | VizQL Data Service (VDS) API | 실측 수치·지표 집계 |
| HTTP 클라이언트 | `httpx` (async) | VDS REST 통신 |
| 런타임 | Python 3.14, `uv` | 의존성 관리 및 실행 |
| 환경 변수 | `python-dotenv` | 인증 정보 분리 |

---

## Project Structure

```
01.Tableau Agent/
├── src/
│   ├── config.py             # TableauConfig + TableauVDSConnector (PAT 인증 베이스)
│   ├── tableau_mcp.py        # ta_mcp FastMCP 서버 (VDS 툴: list_vds_sources, query_vds_data)
│   └── main_agent.py         # 메인 에이전트 진입점 (MultiMCPClient + TableauAgent)
├── docs/
│   ├── architecture_plan.md  # 아키텍처 설계 및 단계별 로드맵
│   └── user_scenarios.md     # 엔드투엔드 유저 시나리오 명세
├── .claude/
│   └── CLAUDE.md             # Claude Code 개발 지침
├── .env                      # 인증 정보 (비공개, git 제외)
├── .env.example              # 환경 변수 템플릿
├── pyproject.toml
└── README.md
```

---

## Installation

```powershell
# 1. 저장소 클론
git clone <repo-url>
cd "01.Tableau Agent"

# 2. 가상환경 생성 및 의존성 설치
uv venv .venv
uv sync

# 3. 환경 변수 설정
copy .env.example .env
# .env 파일을 열어 실제 값 입력
```

## Environment Variables

`.env.example`을 복사하여 `.env`를 생성하고 아래 항목을 채운다.

| 변수 | 필수 | 설명 |
|---|---|---|
| `TABLEAU_VDS_ENDPOINT` | ✅ | Tableau Server/Cloud URL |
| `TABLEAU_PAT_NAME` | ✅ | Personal Access Token 이름 |
| `TABLEAU_PAT_SECRET` | ✅ | Personal Access Token 시크릿 |
| `TABLEAU_SITE_ID` | | 사이트 Content URL (기본 사이트는 빈 문자열) |
| `TABLEAU_OFFICIAL_MCP_CMD` | ✅ | 공식 MCP 서버 실행 명령어 |
| `TABLEAU_OFFICIAL_MCP_ARGS` | ✅ | 공식 MCP 서버 실행 인자 |
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 |
| `AGENT_MODEL` | | LLM 모델 ID (기본값: `claude-sonnet-4-6`) |

## Run

```powershell
# 메인 에이전트 실행
uv run python src/main_agent.py

# ta_mcp 단독 실행 (디버그용)
uv run python src/tableau_mcp.py
```

---

## Documentation

- [아키텍처 설계 및 로드맵](docs/architecture_plan.md)
- [유저 시나리오 명세](docs/user_scenarios.md)

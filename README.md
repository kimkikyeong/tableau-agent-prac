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
| LLM (에이전트) | Claude (Anthropic API) | 의도 파악 및 툴 라우팅 |
| LLM (글로서리 생성) | Gemini (`google-genai` API) | STEP 01 필드 비즈니스 글로서리 자동 생성 (구조화된 출력) |
| MCP 프로토콜 | `mcp` Python SDK | 다중 서버 세션 관리 |
| Tableau 메타데이터 | 공식 Tableau MCP 서버 | 워크북·대시보드·사용자 정보 |
| Tableau 데이터 쿼리 | VizQL Data Service (VDS) API | 실측 수치·지표 집계 |
| 웹 대시보드 | FastAPI + uvicorn + Jinja2 | Agent 대화 / 글로서리 큐레이터 / 분석 가이드라인 통합 UI |
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
│   ├── main_agent.py         # 메인 에이전트 진입점 (MultiMCPClient + TableauAgent)
│   ├── fetch_step01.py       # STEP 01: 데이터 소스·필드 메타데이터·통계 수집 + Gemini 비즈니스 글로서리 자동 생성
│   ├── db.py                 # SQLite 저장소 (datasources/fields/kpis/glossary/field_business_glossary/guidelines/stats 스키마 + snapshot 빌더)
│   ├── health_check.py       # 인프라 헬스 체크 (VDS API, ta_mcp, 공식 MCP) + app_log.json 생성/서빙
│   ├── monitor.html          # STEP 01~05 파이프라인 모니터링 대시보드 (app_log.json 기반 정적 페이지, 읽기 전용)
│   ├── web_app.py            # 통합 웹 대시보드 FastAPI 진입점 (Chat/글로서리 큐레이터/가이드라인 편집)
│   ├── routers/               # web_app 라우터 모듈 (chat.py, glossary.py, guideline.py)
│   ├── templates/index.html  # 통합 대시보드 SPA (Tailwind CDN, 좌측 사이드바 3탭)
│   └── static/style.css      # 대시보드 보강 스타일
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
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 (main_agent.py) |
| `AGENT_MODEL` | | Claude 모델 ID (기본값: `claude-sonnet-4-6`) |
| `GEMINI_API_KEY` | | Gemini API 키 (STEP 01 비즈니스 글로서리 생성, 미설정 시 해당 단계만 스킵) |
| `GEMINI_MODEL` | | Gemini 모델 ID (기본값: `gemini-3.5-flash`) |

## Run

```powershell
# 메인 에이전트 실행
uv run python src/main_agent.py

# ta_mcp 단독 실행 (디버그용)
uv run python src/tableau_mcp.py

# STEP 01: 메타데이터/통계 수집 → metadata.db, app_log.json 생성
uv run python src/fetch_step01.py

# 인프라 헬스 체크 (VDS API / ta_mcp / 공식 MCP), 대시보드 서빙까지 한번에
uv run python src/health_check.py --serve
# → http://localhost:8000/monitor.html 에서 파이프라인 모니터링

# 통합 웹 대시보드 (Chat / 글로서리 큐레이터 / 가이드라인 편집)
uv run uvicorn src.web_app:app --reload
# → http://127.0.0.1:8000
```

---

## Monitoring Dashboard

`src/monitor.html`은 STEP 01~05 파이프라인 진행 상황을 시각화하는 정적 대시보드다. `app_log.json`을 fetch하여 렌더링하며(`file://` 직접 실행 시 목업 데이터로 폴백), 아래 방법 중 하나로 서빙한다.

```powershell
# 방법 1: health_check.py 통합 실행
uv run python src/health_check.py --serve

# 방법 2: 정적 서버만 실행 (app_log.json은 fetch_step01.py / health_check.py로 사전 생성 필요)
cd src
python -m http.server 8000
```

`health_check.py`는 `--watch` 옵션으로 10초 주기 반복 체크도 지원한다. 현재 STEP 01(메타데이터 수집)만 실제 데이터가 반영되며, STEP 02~05는 아직 목업(Phase 2/3 구현 예정) 상태다.

---

## Business Glossary Generation (STEP 01)

`fetch_step01.py`는 데이터소스·필드·통계 수집 직후, **Gemini API**로 필드별 비즈니스 글로서리(표시명·의미·분석 활용법)를 자동 생성하여 `metadata.db`의 `field_business_glossary` 테이블에 저장한다.

- **페르소나**: "병원 경영 분석 스키마 전문 비즈니스 분석가" 시스템 인스트럭션 + VDS 필드 통계(최소/최대/평균 등) 컨텍스트 결합
- **구조화된 출력**: `google-genai` SDK의 `response_schema`(Pydantic `GlossaryItem`)로 JSON 형식을 강제해 파싱 실패를 방지
- **토큰 최적화**: 이미 생성된(또는 `is_confirmed=1`로 승인된) 필드는 재호출하지 않고 스킵 — 배치·오프라인 1회성 생성
- **가이드라인 주입**: `guidelines` 테이블(제목+본문, 여러 건 저장 가능)에 저장된 전체 가이드라인을 `get_guidelines_context_text()`로 합쳐 프롬프트에 함께 전달
- **안전한 스킵**: `GEMINI_API_KEY` 미설정 시 이 단계만 건너뛰고 나머지 STEP 01 파이프라인(수집·통계)은 정상 진행

```powershell
# .env 에 GEMINI_API_KEY 설정 후
uv run python src/fetch_step01.py
```

---

## Web Dashboard

`monitor.html`(읽기 전용 모니터링)과 별개로, 실사용자가 직접 조작하는 통합 웹 대시보드를 FastAPI로 제공한다.

```powershell
uv add fastapi "uvicorn[standard]" jinja2   # 최초 1회
uv run uvicorn src.web_app:app --reload
# → http://127.0.0.1:8000
```

| 탭 | 기능 |
|---|---|
| 💬 Agent 대화방 | `main_agent.py`의 `TableauAgent`를 앱 기동 시 1회 연결해 재사용. 자연어 질문 → 공식 MCP/ta_mcp 툴 라우팅 → 답변. 멀티턴 히스토리 지원 |
| 📖 비즈니스 글로서리 큐레이터 | STEP 01이 생성한 필드 글로서리를 데이터소스별로 조회, 인라인 수정 후 승인(`is_confirmed=1`), 미승인 필드는 Gemini로 개별 재생성 가능 |
| 📝 분석 가이드라인 | 지표별로 제목을 가진 가이드라인을 여러 건 저장. 저장 즉시 Agent 대화(VDS 쿼리 작성)와 STEP 01 글로서리 생성 양쪽의 LLM 프롬프트에 반영 |

라우터는 `src/routers/{chat,glossary,guideline}.py`로 모듈화되어 있으며, `src/web_app.py`의 FastAPI `lifespan`에서 MCP 연결 실패 시에도 글로서리·가이드라인 탭은 정상 동작하도록 격리되어 있다. UI는 `src/templates/index.html` 단일 SPA(Tailwind CDN, 다크/라이트 토글)로 구성된다.

---

## Documentation

- [아키텍처 설계 및 로드맵](docs/architecture_plan.md)
- [유저 시나리오 명세](docs/user_scenarios.md)

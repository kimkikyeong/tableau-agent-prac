"""
Tableau AI Agent 통합 웹 대시보드 — FastAPI 진입점.
Agent 대화(chat), 글로서리 큐레이션(glossary), 분석 가이드라인(guideline) 라우터를 통합하고
Jinja2 템플릿(templates/index.html)과 정적 자원(static/)을 서빙한다.

실행: uv run uvicorn src.web_app:app --reload
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

sys.path.insert(0, str(Path(__file__).parent))
from main_agent import TableauAgent
from routers import chat, glossary, guideline

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 시작 시 MultiMCP 에이전트(공식 Tableau MCP + ta_mcp)를 1회 연결해 재사용한다.
    연결 실패해도(예: MCP 서버 미설치) 서버 자체는 기동해 글로서리/가이드라인 탭은 정상 동작하도록 한다.
    """
    agent = TableauAgent()
    try:
        await agent.__aenter__()
        app.state.agent = agent
    except Exception as e:
        print(f"[web_app] TableauAgent 연결 실패(Chat 탭 비활성화): {e}")
        app.state.agent = None

    try:
        yield
    finally:
        if app.state.agent is not None:
            await app.state.agent.__aexit__(None, None, None)


app = FastAPI(title="Tableau AI Agent Dashboard", lifespan=lifespan)

app.include_router(chat.router, prefix="/api")
app.include_router(glossary.router, prefix="/api")
app.include_router(guideline.router, prefix="/api")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")

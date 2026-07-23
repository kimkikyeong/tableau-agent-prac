"""
메인 에이전트 대화 API.
web_app.py의 lifespan에서 1회 연결한 TableauAgent(공식 Tableau MCP + ta_mcp)를 재사용해
사용자 자연어 질문에 대한 최종 답변을 반환한다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    query: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    answer: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent가 연결되어 있지 않습니다. 서버 로그를 확인하세요.")

    history = [{"role": m.role, "content": m.content} for m in req.history]
    try:
        answer = await agent.run(req.query, history=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 실행 오류: {e}") from e
    return ChatResponse(answer=answer)

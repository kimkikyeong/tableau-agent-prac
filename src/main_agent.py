"""
Tableau Multi-MCP 메인 에이전트.
공식 Tableau MCP (메타데이터/서버 정보)와 ta_mcp (VDS 데이터 쿼리)를 동시에 연결하고,
사용자 질문을 LLM이 적절한 MCP Tool로 자동 라우팅한다.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any

import anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

load_dotenv()

_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")

_SYSTEM_PROMPT = """\
당신은 Tableau 데이터 분석 AI 어시스턴트입니다.
두 개의 MCP 서버가 등록되어 있으며 아래 기준으로 툴을 선택하세요.

[공식 Tableau MCP]
- 워크북, 대시보드, 뷰, 시트, 사용자, 프로젝트 등 Tableau Server/Cloud 메타데이터 조회
- 대시보드 구조, 퍼미션, 사용 현황 등 서버 관리 정보 질문에 사용

[ta_mcp - 커스텀 VDS]
- VDS 데이터 소스 목록 조회 (list_vds_sources)
- 실제 데이터 수치·지표 쿼리 (query_vds_data)
- 매출, 수량, 이익 등 집계·분석이 필요한 질문에 사용

규칙: 툴 호출 전 어떤 서버를 선택했는지 한 줄로 이유를 밝히세요.\
"""


class MultiMCPClient:
    """복수의 MCP 서버 세션을 단일 인터페이스로 관리한다."""

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tool_owner: dict[str, str] = {}   # tool_name → server_name
        self.tools: list[dict[str, Any]] = []   # Anthropic 포맷 툴 목록

    async def connect(self, name: str, params: StdioServerParameters) -> None:
        """MCP 서버 프로세스에 연결하고 툴 목록을 수집한다."""
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions[name] = session

        for tool in (await session.list_tools()).tools:
            self._tool_owner[tool.name] = name
            self.tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            })

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """툴 이름으로 소유 서버를 찾아 실행하고 텍스트 결과를 반환한다."""
        owner = self._tool_owner.get(tool_name)
        if not owner:
            raise ValueError(f"등록되지 않은 툴: '{tool_name}'")
        result = await self._sessions[owner].call_tool(tool_name, arguments)
        return "\n".join(c.text for c in result.content if hasattr(c, "text"))

    async def close(self) -> None:
        await self._exit_stack.aclose()


class TableauAgent:
    """공식 Tableau MCP + ta_mcp를 통합 운영하는 메인 에이전트."""

    def __init__(self) -> None:
        self._mcp = MultiMCPClient()
        self._llm = anthropic.AsyncAnthropic()

    async def _connect_servers(self) -> None:
        # 공식 Tableau MCP — 명령어는 환경 변수로 지정
        official_cmd = os.environ["TABLEAU_OFFICIAL_MCP_CMD"]
        official_args = os.environ.get("TABLEAU_OFFICIAL_MCP_ARGS", "").split()
        await self._mcp.connect(
            "official_tableau_mcp",
            StdioServerParameters(command=official_cmd, args=official_args),
        )

        # ta_mcp — 커스텀 VDS 서버 (현재 프로젝트)
        await self._mcp.connect(
            "ta_mcp",
            StdioServerParameters(
                command="uv",
                args=["run", "python", "src/tableau_mcp.py"],
            ),
        )

    async def run(self, user_query: str) -> str:
        """사용자 질문을 받아 MCP 툴을 활용한 최종 답변을 반환한다."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_query}]

        while True:
            response = await self._llm.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=self._mcp.tools,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                return next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                )

            # 툴 호출 → 결과 수집 → 다음 턴으로 전달
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    raw = await self._mcp.call_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": raw,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    async def __aenter__(self) -> "TableauAgent":
        await self._connect_servers()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._mcp.close()


async def main() -> None:
    async with TableauAgent() as agent:
        while True:
            query = input("\n질문 입력 (종료: q): ").strip()
            if not query or query.lower() == "q":
                break
            answer = await agent.run(query)
            print(f"\n{answer}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Tableau Multi-MCP 메인 에이전트.
공식 Tableau MCP (메타데이터/서버 정보)와 ta_mcp (VDS 데이터 쿼리)를 동시에 연결하고,
사용자 질문을 LLM이 적절한 MCP Tool로 자동 라우팅한다.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

sys.path.insert(0, str(Path(__file__).parent))
import db as metadb

load_dotenv()

_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")

_SYSTEM_PROMPT = """\
당신은 Tableau 데이터 분석 AI 어시스턴트입니다.
두 개의 MCP 서버가 등록되어 있으며, 아래 역할 분리 원칙을 반드시 준수하세요.

## 역할 분리

[공식 Tableau MCP] — 탐색·컨텍스트 수집 담당
- list-datasources       : 데이터 소스 목록 및 LUID 조회
- get-datasource-metadata: 필드 스키마(fieldCaption·타입·집계 기본값) 조회
- search-content         : 자연어로 데이터 소스·워크북 탐색
- get-workbook           : 워크북 내 뷰 목록 및 사용 통계
- list-views             : 뷰 목록 조회
- get-view-data          : 기존 뷰의 데이터를 CSV로 직접 추출
- get-view-image         : 뷰 시각화 이미지 반환

[ta_mcp] — VDS 데이터 쿼리 실행 전담
- query_vds_data: 집계·필터를 포함한 실제 데이터 쿼리 (VizQL Data Service)

## 수치 데이터 조회 시 필수 순서

매출·수량·이익 등 데이터 수치가 필요한 질문은 반드시 아래 3단계를 순서대로 수행하세요.

1단계 [공식 MCP] list-datasources 또는 search-content
  → 사용자가 언급한 데이터 소스의 LUID를 확인한다.

2단계 [공식 MCP] get-datasource-metadata (source_id = 1단계의 LUID)
  → 사용 가능한 fieldCaption 목록과 각 필드의 role(DIMENSION/MEASURE)을 확인한다.

3단계 [ta_mcp] query_vds_data (source_id = 1단계 LUID, fields = 2단계 fieldCaption)
  → 확인된 LUID와 필드명으로 실제 데이터를 조회한다.

## 공식 MCP 단독 사용 (ta_mcp 불필요)

아래 질문은 1·2단계만으로 답변 가능합니다.
- 워크북·대시보드·뷰 목록 또는 구조 파악
- 사용 통계·접근 현황 조회
- 데이터 소스 이름·프로젝트·소유자 등 서버 메타데이터
- 기존 뷰의 데이터를 그대로 추출 (get-view-data)

## 규칙
- 툴 호출 전 어떤 서버를 선택했는지, 현재 몇 단계인지 한 줄로 밝히세요.
- 2단계에서 확인한 fieldCaption을 3단계 fields에 그대로 사용하세요. 임의로 필드명을 추측하지 마세요.
- 아래에 업무 담당자 분석 가이드라인이 주어지면, VDS 쿼리(필드·집계·필터 구성)를 작성할 때 반드시 우선 참고하세요.\
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
        # 공식 Tableau MCP — 명령어는 환경 변수로 지정.
        # 공식 MCP 서버는 SERVER/SITE_NAME/PAT_NAME/PAT_VALUE 이름으로 인증 정보를 기대하므로
        # 프로젝트 표준 환경변수(TABLEAU_VDS_ENDPOINT 등)에서 매핑해 서브프로세스에 전달한다.
        official_cmd = os.environ["TABLEAU_OFFICIAL_MCP_CMD"]
        official_args = os.environ.get("TABLEAU_OFFICIAL_MCP_ARGS", "").split()
        await self._mcp.connect(
            "official_tableau_mcp",
            StdioServerParameters(
                command=official_cmd,
                args=official_args,
                env={
                    **os.environ,
                    "SERVER":    os.environ.get("TABLEAU_VDS_ENDPOINT", "").rstrip("/"),
                    "SITE_NAME": os.environ.get("TABLEAU_SITE_ID", ""),
                    "PAT_NAME":  os.environ.get("TABLEAU_PAT_NAME", ""),
                    "PAT_VALUE": os.environ.get("TABLEAU_PAT_SECRET", ""),
                },
            ),
        )

        # ta_mcp — 커스텀 VDS 서버 (현재 프로젝트)
        await self._mcp.connect(
            "ta_mcp",
            StdioServerParameters(
                command="uv",
                args=["run", "python", "src/tableau_mcp.py"],
            ),
        )

    def _build_system_prompt(self) -> str:
        """저장된 분석 가이드라인 전체를 조회해 시스템 프롬프트에 참고 컨텍스트로 덧붙인다."""
        conn = metadb.init_db()
        try:
            guideline_context = metadb.get_guidelines_context_text(conn)
        finally:
            conn.close()

        if not guideline_context:
            return _SYSTEM_PROMPT
        return f"{_SYSTEM_PROMPT}\n\n## 업무 담당자 분석 가이드라인 (VDS 쿼리 작성 시 우선 참고)\n{guideline_context}"

    async def run(self, user_query: str, history: list[dict[str, Any]] | None = None) -> str:
        """
        사용자 질문을 받아 MCP 툴을 활용한 최종 답변을 반환한다.
        history를 전달하면 이전 turn의 {role, content} 텍스트 메시지를 대화 맥락으로 이어 붙인다.
        저장된 분석 가이드라인은 호출 시점마다 새로 조회해 즉시 반영한다.
        """
        messages: list[dict[str, Any]] = list(history or [])
        messages.append({"role": "user", "content": user_query})
        system_prompt = self._build_system_prompt()

        while True:
            response = await self._llm.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=system_prompt,
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

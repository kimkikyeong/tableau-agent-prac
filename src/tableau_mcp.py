"""
ta_mcp: Tableau 커스텀 MCP 서버.
VDS 데이터 쿼리 및 가드레일 로직을 LLM이 호출 가능한 MCP Tool로 제공한다.
독립 프로세스로 실행: uv run python src/tableau_mcp.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
from config import TableauVDSConnector

server = FastMCP("ta_mcp")


# ---------------------------------------------------------------------------
# 가드레일 헬퍼
# ---------------------------------------------------------------------------

def _require(value: Any, name: str) -> None:
    if not value:
        raise ValueError(f"필수 인자 누락: '{name}'")


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@server.tool()
async def list_vds_sources() -> str:
    """
    사용 가능한 VDS 데이터 소스 목록과 메타데이터를 반환한다.
    실제 데이터 지표 조회 전 반드시 먼저 호출하여 source_id를 확인해야 한다.
    대시보드 구조나 서버 메타데이터가 아닌, 데이터 원본 자체의 목록을 반환한다.
    """
    async with TableauVDSConnector() as conn:
        sources = await conn.get_datasource_metadata()
    return json.dumps(sources, ensure_ascii=False)


@server.tool()
async def query_vds_data(
    source_id: str,
    fields: list[str],
    filters: list[dict] | None = None,
) -> str:
    """
    선택된 VDS 소스에 쿼리를 실행하고 결과를 반환한다.
    수치 분석, 지표 요약, 집계 등 실제 데이터 조회 시 사용한다.

    Args:
        source_id: list_vds_sources()로 획득한 데이터 소스 ID
        fields: 조회할 필드명 목록 (예: ["Sales", "Region", "Profit"])
        filters: 선택적 필터 조건 목록 (예: [{"field": "Region", "value": "East"}])
    """
    # [가드레일 - 사전 검증]
    _require(source_id, "source_id")
    _require(fields, "fields")

    payload: dict[str, Any] = {"fields": fields}
    if filters:
        payload["filters"] = filters

    async with TableauVDSConnector() as conn:
        result = await conn.query(source_id, payload)

    # [가드레일 - 사후 검증]
    if "data" not in result:
        raise RuntimeError(f"VDS 응답에 'data' 키가 없습니다. 원본 응답: {result}")

    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    server.run()

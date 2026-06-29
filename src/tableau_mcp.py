"""
ta_mcp: Tableau 커스텀 MCP 서버 — VDS 쿼리 실행 전담.

역할 분리 원칙:
  - LUID 조회·필드 스키마 탐색: 공식 Tableau MCP (list-datasources, get-datasource-metadata)
  - 실제 데이터 쿼리 실행:      ta_mcp (query_vds_data) ← 이 서버의 유일한 책임

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


def _require(value: Any, name: str) -> None:
    if not value:
        raise ValueError(f"필수 인자 누락: '{name}'")


@server.tool()
async def query_vds_data(
    source_id: str,
    fields: list[str],
    aggregations: dict[str, str] | None = None,
    filters: list[dict] | None = None,
) -> str:
    """
    VDS(VizQL Data Service)를 통해 게시된 데이터 소스에서 실제 데이터를 조회한다.
    매출·수량·이익 등 수치 집계·분석이 필요한 질문에 사용한다.

    호출 전 필수 선행 작업 (공식 Tableau MCP 사용):
      1. list-datasources → source_id(LUID) 확인
      2. get-datasource-metadata → 사용 가능한 fieldCaption 목록 확인

    Args:
        source_id: 공식 MCP list-datasources로 획득한 데이터 소스 LUID
        fields: 공식 MCP get-datasource-metadata에서 확인한 fieldCaption 목록
                (예: ["Category", "Sales", "Profit"])
        aggregations: MEASURE 필드에 적용할 집계 함수
                      (예: {"Sales": "SUM", "Profit": "AVG"})
                      지원값: SUM, AVG, COUNT, COUNTD, MIN, MAX, MEDIAN
        filters: 필터 조건 목록.
                 단일 값: [{"field": "Region", "value": "East"}]
                 복수 값: [{"field": "Category", "values": ["Technology", "Furniture"]}]
                 제외 필터: [{"field": "Segment", "values": ["Home Office"], "exclude": true}]
    """
    _require(source_id, "source_id")
    _require(fields, "fields")

    # fields: list[str] → VDS fields 객체 배열
    vds_fields: list[dict[str, Any]] = []
    for f in fields:
        field_obj: dict[str, Any] = {"fieldCaption": f}
        if aggregations and f in aggregations:
            field_obj["function"] = aggregations[f]
        vds_fields.append(field_obj)

    query_payload: dict[str, Any] = {"fields": vds_fields}

    # filters: 간단한 dict → VDS SET 필터 형식 변환
    if filters:
        vds_filters: list[dict[str, Any]] = []
        for f in filters:
            field_caption = f.get("field")
            if not field_caption:
                continue
            values = f.get("values") or ([f["value"]] if "value" in f else [])
            vds_filters.append({
                "filterType": "SET",
                "field": {"fieldCaption": field_caption},
                "values": [str(v) for v in values],
                "exclude": f.get("exclude", False),
            })
        if vds_filters:
            query_payload["filters"] = vds_filters

    async with TableauVDSConnector() as conn:
        result = await conn.query(source_id, query_payload)

    if "data" not in result:
        raise RuntimeError(f"VDS 응답에 'data' 키가 없습니다. 원본 응답: {result}")

    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    server.run()

"""
비즈니스 글로서리 큐레이션 API.
데이터소스/필드 조회, 표시명·설명·활용법 수정 및 승인(is_confirmed=1), Gemini 단일 필드 재생성을 제공한다.
db.py의 기존 upsert_field_business_glossary 승인 보호 로직(is_confirmed=1인 항목은 덮어쓰지 않음)을 그대로 재사용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import db as metadb
from fetch_step01 import get_gemini_client, regenerate_field_glossary

router = APIRouter(tags=["glossary"])


class GlossaryUpdate(BaseModel):
    logical_name: str
    description: str
    analysis_usage: str


@router.get("/datasources")
async def list_datasources() -> list[dict]:
    conn = metadb.init_db()
    try:
        return metadb.list_datasources(conn)
    finally:
        conn.close()


@router.get("/glossary")
async def get_glossary(
    datasource_luid: str | None = None,
    unconfirmed_only: bool = False,
    search: str | None = None,
) -> list[dict]:
    conn = metadb.init_db()
    try:
        return metadb.get_glossary_rows(conn, datasource_luid, unconfirmed_only, search)
    finally:
        conn.close()


@router.patch("/glossary/{field_id}")
async def update_glossary(field_id: int, body: GlossaryUpdate) -> dict:
    conn = metadb.init_db()
    try:
        row = metadb.get_field_for_glossary(conn, field_id)
        if row is None:
            raise HTTPException(status_code=404, detail="필드를 찾을 수 없습니다.")
        with conn:
            metadb.upsert_field_business_glossary(
                conn, field_id,
                field_name=row["field_caption"],
                logical_name=body.logical_name,
                description=body.description,
                analysis_usage=body.analysis_usage,
                is_confirmed=1,
            )
        return metadb.get_glossary_row(conn, field_id)
    finally:
        conn.close()


@router.post("/glossary/{field_id}/regenerate")
async def regenerate_glossary(field_id: int) -> dict:
    conn = metadb.init_db()
    try:
        row = metadb.get_field_for_glossary(conn, field_id)
        if row is None:
            raise HTTPException(status_code=404, detail="필드를 찾을 수 없습니다.")
        if row["is_confirmed"]:
            raise HTTPException(status_code=409, detail="승인된 필드는 재생성할 수 없습니다.")

        client = get_gemini_client()
        if client is None:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY가 설정되지 않았습니다.")

        ok = await regenerate_field_glossary(client, conn, field_id, metadb.get_guidelines_context_text(conn))
        if not ok:
            raise HTTPException(status_code=502, detail="Gemini 글로서리 생성에 실패했습니다.")
        return metadb.get_glossary_row(conn, field_id)
    finally:
        conn.close()

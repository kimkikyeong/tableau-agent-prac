"""
분석 가이드라인 API.
업무 담당자가 지표별로 작성하는 분석 가이드라인을 제목 단위로 여러 건 저장·수정·삭제한다.
저장된 가이드라인 전체는 db.py의 get_guidelines_context_text()로 합쳐져 Agent 대화(VDS 쿼리 작성)와
STEP 01 글로서리 생성 양쪽의 LLM 프롬프트 컨텍스트로 즉시 반영된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
import db as metadb

router = APIRouter(tags=["guideline"])


class GuidelineBody(BaseModel):
    title: str
    content: str = ""


@router.get("/guidelines")
async def list_guidelines() -> list[dict]:
    conn = metadb.init_db()
    try:
        return metadb.list_guidelines(conn)
    finally:
        conn.close()


@router.get("/guidelines/{guideline_id}")
async def get_guideline(guideline_id: int) -> dict:
    conn = metadb.init_db()
    try:
        row = metadb.get_guideline(conn, guideline_id)
        if row is None:
            raise HTTPException(status_code=404, detail="가이드라인을 찾을 수 없습니다.")
        return row
    finally:
        conn.close()


@router.post("/guidelines")
async def create_guideline(body: GuidelineBody) -> dict:
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="제목은 비어 있을 수 없습니다.")
    conn = metadb.init_db()
    try:
        with conn:
            guideline_id = metadb.create_guideline(conn, body.title.strip(), body.content)
        return metadb.get_guideline(conn, guideline_id)
    finally:
        conn.close()


@router.put("/guidelines/{guideline_id}")
async def update_guideline(guideline_id: int, body: GuidelineBody) -> dict:
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="제목은 비어 있을 수 없습니다.")
    conn = metadb.init_db()
    try:
        with conn:
            ok = metadb.update_guideline(conn, guideline_id, body.title.strip(), body.content)
        if not ok:
            raise HTTPException(status_code=404, detail="가이드라인을 찾을 수 없습니다.")
        return metadb.get_guideline(conn, guideline_id)
    finally:
        conn.close()


@router.delete("/guidelines/{guideline_id}", status_code=204)
async def delete_guideline(guideline_id: int) -> None:
    conn = metadb.init_db()
    try:
        with conn:
            ok = metadb.delete_guideline(conn, guideline_id)
        if not ok:
            raise HTTPException(status_code=404, detail="가이드라인을 찾을 수 없습니다.")
    finally:
        conn.close()

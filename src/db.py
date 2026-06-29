"""
SQLite 메타데이터 저장소.
데이터소스, 필드, 동의어, 글로서리, 소스 간 관계를 영구 보관한다.

DB 위치: src/metadata.db
사용법:
    from db import init_db, upsert_datasource, build_step01_snapshot
    conn = init_db()
    upsert_datasource(conn, ds_dict)
    snapshot = build_step01_snapshot(conn)
    conn.close()
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "metadata.db"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS datasources (
    luid            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    project_name    TEXT NOT NULL DEFAULT '',
    project_id      TEXT NOT NULL DEFAULT '',
    type            TEXT NOT NULL DEFAULT '',
    content_url     TEXT NOT NULL DEFAULT '',
    vds_supported   INTEGER NOT NULL DEFAULT 0,
    skip_reason     TEXT,
    field_count     INTEGER NOT NULL DEFAULT 0,
    collected_at    TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fields (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    datasource_luid     TEXT NOT NULL REFERENCES datasources(luid) ON DELETE CASCADE,
    field_caption       TEXT NOT NULL,
    field_name          TEXT NOT NULL DEFAULT '',
    data_type           TEXT NOT NULL DEFAULT '',
    field_role          TEXT NOT NULL DEFAULT '',
    default_aggregation TEXT NOT NULL DEFAULT '',
    domain              TEXT NOT NULL DEFAULT '',
    collected_at        TEXT NOT NULL,
    UNIQUE (datasource_luid, field_caption)
);

CREATE TABLE IF NOT EXISTS field_synonyms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    synonym     TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'ko',
    source      TEXT NOT NULL DEFAULT 'llm',
    UNIQUE (field_id, synonym)
);

CREATE TABLE IF NOT EXISTS glossaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    project_name TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary_datasources (
    glossary_id     INTEGER NOT NULL REFERENCES glossaries(id) ON DELETE CASCADE,
    datasource_luid TEXT NOT NULL REFERENCES datasources(luid) ON DELETE CASCADE,
    PRIMARY KEY (glossary_id, datasource_luid)
);

CREATE TABLE IF NOT EXISTS datasource_relationships (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_luid   TEXT NOT NULL REFERENCES datasources(luid) ON DELETE CASCADE,
    to_luid     TEXT NOT NULL REFERENCES datasources(luid) ON DELETE CASCADE,
    from_field  TEXT NOT NULL,
    to_field    TEXT NOT NULL,
    confidence  TEXT NOT NULL DEFAULT 'medium',
    source      TEXT NOT NULL DEFAULT 'auto',
    confirmed   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    UNIQUE (from_luid, to_luid, from_field, to_field)
);
"""


def init_db(path: Path = DB_PATH) -> sqlite3.Connection:
    """DB 파일을 열고 스키마를 초기화한 뒤 커넥션을 반환한다."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def upsert_datasource(conn: sqlite3.Connection, data: dict[str, Any]) -> None:
    """
    데이터소스 1건을 upsert한다.
    fields 키가 있으면 기존 필드를 삭제 후 재삽입 (최신 상태 유지).

    data 구조 (fetch_step01.py 결과 dict와 동일):
    {
        luid, name, project, project_id, type, contentUrl,
        vds_supported, field_count, fields: [...], skip_reason (optional)
    }
    """
    now = _now()
    luid = data["luid"]

    conn.execute(
        """
        INSERT INTO datasources
            (luid, name, project_name, project_id, type, content_url,
             vds_supported, skip_reason, field_count, collected_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
            (SELECT collected_at FROM datasources WHERE luid = ?), ?
        ), ?)
        ON CONFLICT(luid) DO UPDATE SET
            name          = excluded.name,
            project_name  = excluded.project_name,
            project_id    = excluded.project_id,
            type          = excluded.type,
            content_url   = excluded.content_url,
            vds_supported = excluded.vds_supported,
            skip_reason   = excluded.skip_reason,
            field_count   = excluded.field_count,
            updated_at    = excluded.updated_at
        """,
        (
            luid,
            data.get("name", ""),
            data.get("project", ""),
            data.get("project_id", ""),
            data.get("type", ""),
            data.get("contentUrl", ""),
            1 if data.get("vds_supported") else 0,
            data.get("skip_reason"),
            data.get("field_count", 0),
            luid, now,  # COALESCE 인자: 기존 collected_at 없으면 now
            now,        # updated_at
        ),
    )

    fields: list[dict] = data.get("fields", [])
    if fields:
        conn.execute("DELETE FROM fields WHERE datasource_luid = ?", (luid,))
        conn.executemany(
            """
            INSERT INTO fields
                (datasource_luid, field_caption, field_name,
                 data_type, field_role, default_aggregation, domain, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    luid,
                    f.get("name", ""),
                    f.get("fieldName", ""),
                    f.get("type", ""),
                    f.get("role", ""),
                    f.get("defaultAggregation", ""),
                    f.get("domain", ""),
                    now,
                )
                for f in fields
            ],
        )


def upsert_all(conn: sqlite3.Connection, results: list[dict[str, Any]]) -> None:
    """수집 결과 전체를 트랜잭션 단위로 upsert한다."""
    with conn:
        for ds in results:
            upsert_datasource(conn, ds)


def build_step01_snapshot(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """
    metadata.db에서 step01 데이터를 읽어 app_log.json용 snapshot dict를 반환한다.
    DB가 비어있으면 None 반환.
    """
    rows = conn.execute(
        "SELECT * FROM datasources ORDER BY project_name, name"
    ).fetchall()
    if not rows:
        return None

    sources: list[dict] = []
    for row in rows:
        luid = row["luid"]
        field_rows = conn.execute(
            """
            SELECT f.field_caption, f.field_name, f.data_type,
                   f.field_role, f.default_aggregation, f.domain,
                   GROUP_CONCAT(s.synonym, '||') AS synonyms_raw
            FROM fields f
            LEFT JOIN field_synonyms s ON s.field_id = f.id
            WHERE f.datasource_luid = ?
            GROUP BY f.id
            ORDER BY f.id
            """,
            (luid,),
        ).fetchall()

        fields = [
            {
                "name":               fr["field_caption"],
                "fieldName":          fr["field_name"],
                "type":               fr["data_type"],
                "role":               fr["field_role"],
                "defaultAggregation": fr["default_aggregation"],
                "domain":             fr["domain"],
                "synonyms": fr["synonyms_raw"].split("||") if fr["synonyms_raw"] else [],
            }
            for fr in field_rows
        ]

        sources.append(
            {
                "luid":          luid,
                "name":          row["name"],
                "project":       row["project_name"],
                "project_id":    row["project_id"],
                "type":          row["type"],
                "contentUrl":    row["content_url"],
                "vds_supported": bool(row["vds_supported"]),
                "field_count":   row["field_count"],
                "fields":        fields,
                **({"skip_reason": row["skip_reason"]} if row["skip_reason"] else {}),
            }
        )

    total_fields = sum(r["field_count"] for r in sources if r["vds_supported"])

    glossary_rows = conn.execute(
        """
        SELECT g.id, g.name, g.project_name,
               GROUP_CONCAT(gd.datasource_luid, '||') AS luids
        FROM glossaries g
        LEFT JOIN glossary_datasources gd ON gd.glossary_id = g.id
        GROUP BY g.id
        ORDER BY g.name
        """
    ).fetchall()

    glossaries: list[dict] = []
    assigned_luids: set[str] = set()
    for gr in glossary_rows:
        luids = set(gr["luids"].split("||")) if gr["luids"] else set()
        assigned_luids |= luids
        ds_in_glossary = [s for s in sources if s["luid"] in luids]
        glossaries.append(
            {
                "project_name": gr["name"],
                "project_id":   gr["project_name"],
                "datasources":  ds_in_glossary,
            }
        )

    unassigned = [s for s in sources if s["luid"] not in assigned_luids]

    updated_at_row = conn.execute(
        "SELECT MAX(updated_at) AS ts FROM datasources"
    ).fetchone()

    return {
        "status":             "done",
        "last_run":           updated_at_row["ts"] or _now(),
        "glossary_count":     len(glossaries),
        "fields_profiled":    total_fields,
        "glossaries":         glossaries,
        "unassigned_sources": unassigned,
    }


def get_relationship_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    동일한 field_name이 2개 이상 데이터소스에 존재하는 경우를 조인 키 후보로 반환한다.
    결과: [{from_luid, from_name, to_luid, to_name, field_name, confidence}]
    """
    rows = conn.execute(
        """
        SELECT
            f1.datasource_luid AS from_luid,
            d1.name            AS from_name,
            f2.datasource_luid AS to_luid,
            d2.name            AS to_name,
            f1.field_name      AS field_name
        FROM fields f1
        JOIN fields f2
          ON  f1.field_name      = f2.field_name
          AND f1.datasource_luid < f2.datasource_luid
          AND f1.field_name     != ''
        JOIN datasources d1 ON d1.luid = f1.datasource_luid
        JOIN datasources d2 ON d2.luid = f2.datasource_luid
        WHERE d1.vds_supported = 1 AND d2.vds_supported = 1
        ORDER BY f1.field_name, d1.name, d2.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

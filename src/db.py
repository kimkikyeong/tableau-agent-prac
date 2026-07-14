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

DROP TABLE IF EXISTS glossary_datasources;
DROP TABLE IF EXISTS glossaries;

CREATE TABLE IF NOT EXISTS kpis (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kpi_datasources (
    kpi_id          INTEGER NOT NULL REFERENCES kpis(id) ON DELETE CASCADE,
    datasource_luid TEXT NOT NULL REFERENCES datasources(luid) ON DELETE CASCADE,
    PRIMARY KEY (kpi_id, datasource_luid)
);

CREATE TABLE IF NOT EXISTS kpi_glossary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kpi_id        INTEGER NOT NULL REFERENCES kpis(id) ON DELETE CASCADE,
    field_id      INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    business_term TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    UNIQUE (kpi_id, field_id)
);

CREATE TABLE IF NOT EXISTS field_stats (
    field_id       INTEGER PRIMARY KEY REFERENCES fields(id) ON DELETE CASCADE,
    non_null_count INTEGER,
    distinct_count INTEGER,
    min_value      TEXT,
    max_value      TEXT,
    mean_value     REAL,
    top_values     TEXT,
    collected_at   TEXT NOT NULL
);

-- KPI 미배정 상태에서도 유효한 필드 단위 비즈니스 글로서리 (LLM 자동 생성).
-- kpi_glossary는 KPI-필드 조합에 종속되므로, KPI 배정 이전 단계의
-- 필드 자체의 표시명·의미·활용법을 저장하기 위해 별도 테이블로 분리한다.
CREATE TABLE IF NOT EXISTS field_business_glossary (
    field_id        INTEGER PRIMARY KEY REFERENCES fields(id) ON DELETE CASCADE,
    field_name      TEXT NOT NULL DEFAULT '',
    logical_name    TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    analysis_usage  TEXT NOT NULL DEFAULT '',
    is_confirmed    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
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
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """기존 DB에 누락된 컬럼을 추가하는 단계적 마이그레이션."""
    migrations = [
        "ALTER TABLE field_stats ADD COLUMN top_values TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass  # 이미 존재하는 컬럼이면 무시


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
    metadata.db에서 KPI·데이터소스·필드를 읽어 app_log.json용 snapshot dict를 반환한다.
    DB가 비어있으면 None 반환.
    """
    ds_rows = conn.execute(
        "SELECT * FROM datasources ORDER BY project_name, name"
    ).fetchall()
    if not ds_rows:
        return None

    # ── 데이터소스별 필드 로드 (field DB id는 내부 글로서리 조회용) ──
    fields_map: dict[str, list[dict]] = {}
    field_id_map: dict[str, list[int]] = {}

    for row in ds_rows:
        luid = row["luid"]
        frows = conn.execute(
            """
            SELECT f.id, f.field_caption, f.field_name, f.data_type,
                   f.field_role, f.default_aggregation, f.domain,
                   GROUP_CONCAT(s.synonym, '||') AS synonyms_raw,
                   fs.non_null_count, fs.distinct_count,
                   fs.min_value, fs.max_value, fs.mean_value, fs.top_values,
                   bg.logical_name, bg.description AS bg_description,
                   bg.analysis_usage, bg.is_confirmed
            FROM fields f
            LEFT JOIN field_synonyms s  ON s.field_id  = f.id
            LEFT JOIN field_stats    fs ON fs.field_id = f.id
            LEFT JOIN field_business_glossary bg ON bg.field_id = f.id
            WHERE f.datasource_luid = ?
            GROUP BY f.id ORDER BY f.id
            """,
            (luid,),
        ).fetchall()
        fields_map[luid] = [
            {
                "name":               fr["field_caption"],
                "fieldName":          fr["field_name"],
                "type":               fr["data_type"],
                "role":               fr["field_role"],
                "defaultAggregation": fr["default_aggregation"],
                "domain":             fr["domain"],
                "synonyms": fr["synonyms_raw"].split("||") if fr["synonyms_raw"] else [],
                "stats": {
                    "non_null_count": fr["non_null_count"],
                    "distinct_count": fr["distinct_count"],
                    "min_value":      fr["min_value"],
                    "max_value":      fr["max_value"],
                    "mean_value":     round(fr["mean_value"], 2) if fr["mean_value"] is not None else None,
                    "top_values":     __import__("json").loads(fr["top_values"]) if fr["top_values"] else None,
                } if fr["non_null_count"] is not None else None,
                "business_glossary": {
                    "logical_name":   fr["logical_name"],
                    "description":    fr["bg_description"],
                    "analysis_usage": fr["analysis_usage"],
                    "is_confirmed":   bool(fr["is_confirmed"]),
                } if fr["logical_name"] is not None else None,
            }
            for fr in frows
        ]
        field_id_map[luid] = [fr["id"] for fr in frows]

    def _make_source(row: sqlite3.Row, fields: list[dict]) -> dict:
        d: dict[str, Any] = {
            "luid":          row["luid"],
            "name":          row["name"],
            "project":       row["project_name"],
            "project_id":    row["project_id"],
            "type":          row["type"],
            "contentUrl":    row["content_url"],
            "vds_supported": bool(row["vds_supported"]),
            "field_count":   row["field_count"],
            "fields":        fields,
        }
        if row["skip_reason"]:
            d["skip_reason"] = row["skip_reason"]
        return d

    ds_row_map = {row["luid"]: row for row in ds_rows}
    total_fields = sum(row["field_count"] for row in ds_rows if row["vds_supported"])

    # ── KPI별 데이터소스·글로서리 수집 ──
    kpi_rows = conn.execute("SELECT * FROM kpis ORDER BY name").fetchall()
    kpis: list[dict] = []
    assigned_luids: set[str] = set()

    for kpi_row in kpi_rows:
        kpi_id = kpi_row["id"]

        linked_rows = conn.execute(
            "SELECT datasource_luid FROM kpi_datasources WHERE kpi_id = ?",
            (kpi_id,),
        ).fetchall()

        datasources: list[dict] = []
        for lr in linked_rows:
            luid = lr["datasource_luid"]
            if luid not in ds_row_map:
                continue
            assigned_luids.add(luid)

            # KPI 내 글로서리 (field_id → row)
            gloss_rows = conn.execute(
                """
                SELECT kg.field_id, kg.business_term, kg.description
                FROM kpi_glossary kg
                WHERE kg.kpi_id = ?
                  AND kg.field_id IN (SELECT id FROM fields WHERE datasource_luid = ?)
                """,
                (kpi_id, luid),
            ).fetchall()
            gloss = {gr["field_id"]: gr for gr in gloss_rows}

            db_ids = field_id_map.get(luid, [])
            enriched: list[dict] = []
            for i, f in enumerate(fields_map.get(luid, [])):
                ef = dict(f)
                fid = db_ids[i] if i < len(db_ids) else None
                if fid and fid in gloss:
                    ef["business_term"] = gloss[fid]["business_term"]
                    ef["gloss_desc"]    = gloss[fid]["description"]
                enriched.append(ef)

            datasources.append(_make_source(ds_row_map[luid], enriched))

        kpis.append({
            "id":          kpi_row["id"],
            "name":        kpi_row["name"],
            "description": kpi_row["description"],
            "datasources": datasources,
        })

    unassigned = [
        _make_source(ds_row_map[luid], fields_map.get(luid, []))
        for luid in ds_row_map
        if luid not in assigned_luids
    ]

    updated_at_row = conn.execute(
        "SELECT MAX(updated_at) AS ts FROM datasources"
    ).fetchone()

    return {
        "status":             "done",
        "last_run":           updated_at_row["ts"] or _now(),
        "kpi_count":          len(kpis),
        "fields_profiled":    total_fields,
        "kpis":               kpis,
        "unassigned_sources": unassigned,
    }


def upsert_field_stats(
    conn: sqlite3.Connection,
    field_id: int,
    non_null_count: int | None,
    distinct_count: int | None,
    min_value: str | None,
    max_value: str | None,
    mean_value: float | None,
    top_values: list[str] | None = None,
) -> None:
    """필드 기술통계를 upsert한다."""
    import json as _json
    top_values_json = _json.dumps(top_values, ensure_ascii=False) if top_values is not None else None
    conn.execute(
        """
        INSERT INTO field_stats
            (field_id, non_null_count, distinct_count, min_value, max_value, mean_value, top_values, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(field_id) DO UPDATE SET
            non_null_count = excluded.non_null_count,
            distinct_count = excluded.distinct_count,
            min_value      = excluded.min_value,
            max_value      = excluded.max_value,
            mean_value     = excluded.mean_value,
            top_values     = excluded.top_values,
            collected_at   = excluded.collected_at
        """,
        (field_id, non_null_count, distinct_count, min_value, max_value, mean_value, top_values_json, _now()),
    )


def get_fields_missing_glossary(conn: sqlite3.Connection, datasource_luid: str) -> list[dict[str, Any]]:
    """
    field_business_glossary가 아직 생성되지 않은 필드를 통계와 함께 반환한다.
    LLM 글로서리 생성 대상을 선별해 배치 1회 생성 원칙(토큰 최적화)을 지키기 위한 조회.
    """
    rows = conn.execute(
        """
        SELECT f.id, f.field_caption, f.field_name, f.data_type,
               f.field_role, f.default_aggregation,
               fs.non_null_count, fs.distinct_count,
               fs.min_value, fs.max_value, fs.mean_value
        FROM fields f
        LEFT JOIN field_stats fs ON fs.field_id = f.id
        WHERE f.datasource_luid = ?
          AND f.id NOT IN (SELECT field_id FROM field_business_glossary)
        ORDER BY f.id
        """,
        (datasource_luid,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_field_business_glossary(
    conn: sqlite3.Connection,
    field_id: int,
    field_name: str,
    logical_name: str,
    description: str,
    analysis_usage: str,
    is_confirmed: int = 0,
) -> None:
    """
    필드 단위 LLM 생성 비즈니스 글로서리를 upsert한다.
    is_confirmed=1(현업 담당자 승인)로 확정된 항목은 재생성 결과로 덮어쓰지 않는다.
    """
    now = _now()
    conn.execute(
        """
        INSERT INTO field_business_glossary
            (field_id, field_name, logical_name, description, analysis_usage, is_confirmed, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(field_id) DO UPDATE SET
            field_name     = excluded.field_name,
            logical_name   = excluded.logical_name,
            description    = excluded.description,
            analysis_usage = excluded.analysis_usage,
            updated_at     = excluded.updated_at
        WHERE field_business_glossary.is_confirmed = 0
        """,
        (field_id, field_name, logical_name, description, analysis_usage, is_confirmed, now, now),
    )


def upsert_kpi(conn: sqlite3.Connection, name: str, description: str = "") -> int:
    """KPI를 이름으로 upsert하고 id를 반환한다."""
    now = _now()
    conn.execute(
        """
        INSERT INTO kpis (name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            description = excluded.description,
            updated_at  = excluded.updated_at
        """,
        (name, description, now, now),
    )
    row = conn.execute("SELECT id FROM kpis WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def link_kpi_datasource(conn: sqlite3.Connection, kpi_id: int, datasource_luid: str) -> None:
    """KPI에 데이터소스를 연결한다. 이미 연결되어 있으면 무시한다."""
    conn.execute(
        "INSERT OR IGNORE INTO kpi_datasources (kpi_id, datasource_luid) VALUES (?, ?)",
        (kpi_id, datasource_luid),
    )


def unlink_kpi_datasource(conn: sqlite3.Connection, kpi_id: int, datasource_luid: str) -> None:
    """KPI에서 데이터소스 연결을 해제한다."""
    conn.execute(
        "DELETE FROM kpi_datasources WHERE kpi_id = ? AND datasource_luid = ?",
        (kpi_id, datasource_luid),
    )


def upsert_kpi_glossary(
    conn: sqlite3.Connection,
    kpi_id: int,
    field_id: int,
    business_term: str = "",
    description: str = "",
) -> None:
    """KPI 내 필드의 비즈니스 용어·설명을 upsert한다."""
    now = _now()
    conn.execute(
        """
        INSERT INTO kpi_glossary (kpi_id, field_id, business_term, description, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(kpi_id, field_id) DO UPDATE SET
            business_term = excluded.business_term,
            description   = excluded.description
        """,
        (kpi_id, field_id, business_term, description, now),
    )


def get_kpis(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """KPI 목록과 연결된 데이터소스 수를 반환한다."""
    rows = conn.execute(
        """
        SELECT k.id, k.name, k.description, k.created_at, k.updated_at,
               COUNT(kd.datasource_luid) AS ds_count
        FROM kpis k
        LEFT JOIN kpi_datasources kd ON kd.kpi_id = k.id
        GROUP BY k.id
        ORDER BY k.name
        """
    ).fetchall()
    return [dict(r) for r in rows]


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

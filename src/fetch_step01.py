"""
STEP 01 데이터 수집 스크립트.
Tableau Cloud 전체 데이터 소스 목록 및 VDS 필드 메타데이터를 수집하여
src/metadata.db 에 저장하고, 모니터 표시용 스냅샷을 src/app_log.json 에 기록한다.

실행: uv run python src/fetch_step01.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import TableauVDSConnector
import db as metadb

OUT_PATH       = Path(__file__).parent / "app_log.json"
MAX_CONCURRENT = 5


async def _fetch_fields(
    conn: TableauVDSConnector,
    source: dict,
    semaphore: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    """단일 데이터 소스의 VDS 필드 메타데이터를 조회한다."""
    luid = source.get("id", "")
    name = source.get("name", "")

    async with semaphore:
        try:
            meta   = await conn.get_vds_metadata(luid)
            raw    = meta.get("data", [])
            fields = [
                {
                    "name":               f.get("fieldCaption") or f.get("fieldName", ""),
                    "fieldName":          f.get("fieldName", ""),
                    "type":               f.get("dataType", ""),
                    "role":               f.get("fieldRole", ""),
                    "defaultAggregation": f.get("defaultAggregation", ""),
                    "domain":             "",
                    "synonyms":           [],
                }
                for f in raw
                if not f.get("hidden", False) and (f.get("fieldCaption") or f.get("fieldName"))
            ]
            print(f"  [{idx:>3}/{total}] [OK  ] {name[:50]:<50}  필드 {len(fields):>3}개")
            return {
                "luid":          luid,
                "name":          name,
                "project":       source.get("project", {}).get("name", ""),
                "project_id":    source.get("project", {}).get("id", ""),
                "type":          source.get("type", ""),
                "contentUrl":    source.get("contentUrl", ""),
                "vds_supported": True,
                "field_count":   len(fields),
                "fields":        fields,
            }
        except Exception as e:
            short_err = str(e)[:80]
            print(f"  [{idx:>3}/{total}] [SKIP] {name[:50]:<50}  {short_err}")
            return {
                "luid":          luid,
                "name":          name,
                "project":       source.get("project", {}).get("name", ""),
                "project_id":    source.get("project", {}).get("id", ""),
                "type":          source.get("type", ""),
                "contentUrl":    source.get("contentUrl", ""),
                "vds_supported": False,
                "field_count":   0,
                "fields":        [],
                "skip_reason":   short_err,
            }


def _write_app_log(db_conn, infra_override: dict | None = None) -> None:
    """
    metadata.db 에서 step01 스냅샷을 읽어 app_log.json 을 갱신한다.
    기존 app_log.json 의 infrastructure 및 다른 steps 는 보존한다.
    """
    existing: dict = {}
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    step01 = metadb.build_step01_snapshot(db_conn)
    if step01 is None:
        return

    log: dict = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "infrastructure": infra_override or existing.get("infrastructure", {}),
        "steps": {
            **existing.get("steps", {}),
            "step01": step01,
        },
    }
    OUT_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> None:
    print("=" * 65)
    print("  STEP 01 - Data Source & VDS Field Metadata Collection")
    print("=" * 65)

    async with TableauVDSConnector() as conn:
        print("\n[1/2] 데이터 소스 목록 조회 중...")
        sources = await conn.get_datasource_metadata()
        print(f"      발견: {len(sources)}개\n")

        print(f"[2/2] VDS 필드 메타데이터 수집 (동시 {MAX_CONCURRENT}건)...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        results   = await asyncio.gather(*[
            _fetch_fields(conn, s, semaphore, i + 1, len(sources))
            for i, s in enumerate(sources)
        ])

    ok   = [r for r in results if r["vds_supported"]]
    skip = [r for r in results if not r["vds_supported"]]
    total_fields = sum(r["field_count"] for r in ok)

    print(f"\n{'─' * 65}")
    print(f"  VDS 지원: {len(ok):>3}개  |  미지원/오류: {len(skip):>3}개  |  총 필드: {total_fields}개")
    print(f"{'─' * 65}")

    # metadata.db 에 저장
    print("\n[DB] metadata.db 저장 중...")
    db_conn = metadb.init_db()
    metadb.upsert_all(db_conn, results)
    print(f"     저장 완료: {metadb.DB_PATH.resolve()}")

    # app_log.json 스냅샷 갱신
    _write_app_log(db_conn)
    db_conn.close()

    print(f"\n스냅샷 저장: {OUT_PATH.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())

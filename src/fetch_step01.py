"""
STEP 01 데이터 수집 스크립트.
Tableau Cloud 전체 데이터 소스 목록 및 VDS 필드 메타데이터를 수집하여
src/metadata.db 에 저장하고, 모니터 표시용 스냅샷을 src/app_log.json 에 기록한다.

실행: uv run python src/fetch_step01.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))
from config import TableauVDSConnector
import db as metadb

OUT_PATH       = Path(__file__).parent / "app_log.json"
MAX_CONCURRENT = 5

# ── LLM 비즈니스 글로서리 생성 설정 (Gemini) ──
GLOSSARY_MODEL       = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GLOSSARY_CONCURRENT  = 3
GUIDELINE_PATH       = Path(__file__).parent / "guideline.txt"

GLOSSARY_SYSTEM_PROMPT = """\
당신은 병원 경영 분석 스키마 전문 비즈니스 분석가입니다.
Tableau 데이터 소스의 필드 메타데이터(원본명·타입·역할·기술통계)를 보고, \
현업 담당자가 이해할 수 있는 비즈니스 글로서리를 필드별로 생성합니다.

각 필드마다 다음 세 가지를 정의하세요.
- logical_name   : 비즈니스 표시명 (간결한 한글 명사형)
- description    : 필드가 나타내는 비즈니스 의미
- analysis_usage : 실제 KPI/비즈니스 분석에서의 구체적 활용 시나리오

예시:
- hospital → 병원: 분석 대상 병원을 나타내는 표시명입니다. 병원별 실행수익(매출/수익) 및 구성항목을 비교할 때 사용합니다.
- vat_amount → 부가세금액: 부가가치세 관련 금액을 의미합니다. 세금 포함/제외 매출 비교나 수익 산정 시 세금 구성 확인에 활용됩니다.

지정된 JSON 스키마 형식으로만 응답하고, 입력받은 필드 개수와 동일한 개수의 항목을 채우세요.\
"""


class GlossaryItem(BaseModel):
    """Gemini 구조화된 출력 스키마 — 필드 1개의 비즈니스 글로서리."""
    field_name: str
    logical_name: str
    description: str
    analysis_usage: str


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


def _stat_extract(row: dict, caption: str, func: str):
    """VDS 응답 row에서 FUNC(caption) 패턴의 키를 찾아 값을 반환한다."""
    # Tableau VDS가 반환하는 열 이름 형식: "FUNC(caption)" 또는 "FUNC(fieldName)"
    # CNT/CNTD 는 COUNT/COUNTD 의 내부 약어
    aliases = {
        "COUNT": ["COUNT", "CNT"],
        "COUNTD": ["COUNTD", "CNTD"],
    }
    funcs_to_try = aliases.get(func.upper(), [func.upper()])
    for f in funcs_to_try:
        exact = f"{f}({caption})"
        if exact in row:
            return row[exact]
    # 폴백: 대소문자 무시, 키에 func와 caption 모두 포함
    cap_lower  = caption.lower()
    for key, val in row.items():
        ku = key.lower()
        if cap_lower in ku and any(f.lower() in ku for f in funcs_to_try):
            return val
    return None


async def _compute_field_stats(
    conn: TableauVDSConnector,
    luid: str,
    fields: list[dict],
) -> dict[str, dict]:
    """
    VDS 집계 쿼리 2회(측도/차원)로 각 필드의 기술통계를 반환한다.
    반환: {field_caption: {non_null_count, distinct_count, min_value, max_value, mean_value}}
    """
    measures = [f for f in fields if f.get("role") == "MEASURE"]
    dims     = [f for f in fields if f.get("role") != "MEASURE"]
    stats: dict[str, dict] = {}

    # ── 측도: COUNT, COUNTD, MIN, MAX, AVG ──
    if measures:
        qfields = [
            {"fieldCaption": f["name"], "function": func}
            for f in measures
            for func in ["COUNT", "COUNTD", "MIN", "MAX", "AVG"]
        ]
        try:
            result = await conn.query(luid, {"fields": qfields})
            if result.get("data"):
                row = result["data"][0]
                for f in measures:
                    n = f["name"]
                    raw_min = _stat_extract(row, n, "MIN")
                    raw_max = _stat_extract(row, n, "MAX")
                    raw_avg = _stat_extract(row, n, "AVG")
                    stats[n] = {
                        "non_null_count": _stat_extract(row, n, "COUNT"),
                        "distinct_count": _stat_extract(row, n, "COUNTD"),
                        "min_value":  str(raw_min) if raw_min is not None else None,
                        "max_value":  str(raw_max) if raw_max is not None else None,
                        "mean_value": float(raw_avg) if raw_avg is not None else None,
                    }
        except Exception as e:
            print(f"    [STAT] 측도 집계 오류 ({luid[:8]}): {e}")

    # ── 차원: COUNT, COUNTD ──
    if dims:
        qfields = [
            {"fieldCaption": f["name"], "function": func}
            for f in dims
            for func in ["COUNT", "COUNTD"]
        ]
        try:
            result = await conn.query(luid, {"fields": qfields})
            if result.get("data"):
                row = result["data"][0]
                for f in dims:
                    n = f["name"]
                    stats[n] = {
                        "non_null_count": _stat_extract(row, n, "COUNT"),
                        "distinct_count": _stat_extract(row, n, "COUNTD"),
                        "min_value":  None,
                        "max_value":  None,
                        "mean_value": None,
                    }
        except Exception as e:
            print(f"    [STAT] 차원 집계 오류 ({luid[:8]}): {e}")

    return stats


async def _fetch_and_save_stats(
    conn: TableauVDSConnector,
    db_conn,
    result: dict,
    semaphore: asyncio.Semaphore,
) -> None:
    """단일 데이터소스의 기술통계를 수집해 DB에 저장한다."""
    luid   = result["luid"]
    name   = result["name"]
    fields = result["fields"]

    fid_map = {
        row["field_caption"]: row["id"]
        for row in db_conn.execute(
            "SELECT id, field_caption FROM fields WHERE datasource_luid = ?", (luid,)
        ).fetchall()
    }

    async with semaphore:
        stats = await _compute_field_stats(conn, luid, fields)

    with db_conn:
        for f in fields:
            fname = f["name"]
            fid   = fid_map.get(fname)
            if fid and fname in stats:
                s = stats[fname]
                metadb.upsert_field_stats(
                    db_conn, fid,
                    non_null_count=s.get("non_null_count"),
                    distinct_count=s.get("distinct_count"),
                    min_value=s.get("min_value"),
                    max_value=s.get("max_value"),
                    mean_value=s.get("mean_value"),
                )

    collected = sum(1 for f in fields if f["name"] in stats)
    print(f"  [STAT] {name[:50]:<50}  {collected}/{len(fields)}개 필드 완료")


def _load_guideline() -> str | None:
    """업무 담당자가 작성한 구술형 가이드라인 텍스트(src/guideline.txt)가 있으면 로드한다."""
    if GUIDELINE_PATH.exists():
        text = GUIDELINE_PATH.read_text(encoding="utf-8").strip()
        return text or None
    return None


async def _generate_datasource_glossary(
    client: genai.Client,
    db_conn,
    luid: str,
    name: str,
    semaphore: asyncio.Semaphore,
    guideline: str | None,
) -> None:
    """
    데이터소스 1건에서 글로서리가 없는 필드만 골라 Gemini로 생성하고 DB에 저장한다.
    이미 생성된(또는 승인된) 필드는 get_fields_missing_glossary에서 걸러지므로
    배치 실행 시 최초 1회만 LLM을 호출한다 (토큰 최적화).
    """
    targets = metadb.get_fields_missing_glossary(db_conn, luid)
    if not targets:
        return

    context = [
        {
            "field_name": f["field_caption"],
            "data_type":  f["data_type"],
            "role":       f["field_role"],
            "aggregation": f["default_aggregation"],
            "stats": {
                "non_null_count": f["non_null_count"],
                "distinct_count": f["distinct_count"],
                "min_value":      f["min_value"],
                "max_value":      f["max_value"],
                "mean_value":     f["mean_value"],
            } if f["non_null_count"] is not None else None,
        }
        for f in targets
    ]

    user_prompt = f"데이터 소스: {name}\n필드 메타데이터:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    if guideline:
        user_prompt += f"\n\n업무 담당자 가이드라인 (참고):\n{guideline}"

    config = types.GenerateContentConfig(
        system_instruction=GLOSSARY_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=list[GlossaryItem],
        max_output_tokens=4096,
    )

    async with semaphore:
        try:
            response = await client.aio.models.generate_content(
                model=GLOSSARY_MODEL,
                contents=user_prompt,
                config=config,
            )
        except Exception as e:
            print(f"    [GLOSS] LLM 호출 오류 ({name[:30]}): {e}")
            return

    items: list[GlossaryItem] = response.parsed or []
    if not items:
        # response_schema 검증 실패 등으로 parsed가 비어있으면 원문 JSON을 직접 파싱 시도
        try:
            items = [GlossaryItem.model_validate(i) for i in json.loads(response.text)]
        except Exception:
            print(f"    [GLOSS] 응답 파싱 실패 ({name[:30]})")
            return

    fid_map = {f["field_caption"]: f["id"] for f in targets}
    saved = 0
    with db_conn:
        for item in items:
            fid = fid_map.get(item.field_name)
            if fid is None:
                continue
            metadb.upsert_field_business_glossary(
                db_conn, fid,
                field_name=item.field_name,
                logical_name=item.logical_name,
                description=item.description,
                analysis_usage=item.analysis_usage,
            )
            saved += 1
    print(f"  [GLOSS] {name[:50]:<50}  {saved}/{len(targets)}개 필드 완료")


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


# TODO: 임시 필터 상수 — 운영 시 None 으로 변경
_FILTER_ROOT_PROJECT = "김기경"


async def _collect_descendant_project_ids(conn: TableauVDSConnector, root_name: str) -> set[str]:
    """
    root_name 프로젝트 및 모든 하위 프로젝트의 id를 재귀로 수집한다.
    데이터소스 API는 직접 소속 프로젝트 id만 반환하므로 트리 전체 id가 필요하다.
    """
    cfg = conn._config
    client = conn._client
    ver = cfg.api_version
    site = conn._site_luid

    projects: list[dict] = []
    page = 1
    while True:
        r = await client.get(
            f"/api/{ver}/sites/{site}/projects",
            params={"pageSize": 100, "pageNumber": page},
        )
        r.raise_for_status()
        body = r.json()
        batch = body["projects"]["project"]
        projects.extend(batch)
        total = int(body["pagination"]["totalAvailable"])
        if len(projects) >= total:
            break
        page += 1

    # root 탐색
    root = next((p for p in projects if p["name"] == root_name), None)
    if root is None:
        return set()

    # 자식 → 부모 맵으로 재귀 없이 BFS
    children: dict[str, list[str]] = {}
    for p in projects:
        parent = p.get("parentProjectId")
        if parent:
            children.setdefault(parent, []).append(p["id"])

    result: set[str] = set()
    queue = [root["id"]]
    while queue:
        pid = queue.pop()
        result.add(pid)
        queue.extend(children.get(pid, []))
    return result


async def main() -> None:
    print("=" * 65)
    print("  STEP 01 - Data Source & VDS Field Metadata Collection")
    print("=" * 65)

    async with TableauVDSConnector() as conn:
        print("\n[1/4] 데이터 소스 목록 조회 중...")
        sources = await conn.get_datasource_metadata()
        print(f"      전체 발견: {len(sources)}개")

        # TODO: 임시 필터 — _FILTER_ROOT_PROJECT 프로젝트 및 하위 전체
        if _FILTER_ROOT_PROJECT:
            target_ids = await _collect_descendant_project_ids(conn, _FILTER_ROOT_PROJECT)
            print(f"      대상 프로젝트 id ({_FILTER_ROOT_PROJECT} 포함 하위): {len(target_ids)}개")
            sources = [s for s in sources if s.get("project", {}).get("id", "") in target_ids]
            print(f"      필터 후: {len(sources)}개\n")

        print(f"[2/4] VDS 필드 메타데이터 수집 (동시 {MAX_CONCURRENT}건)...")
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

        # DB 저장 (field_id 확보 목적)
        print("\n[DB] metadata.db 저장 중...")
        db_conn = metadb.init_db()
        metadb.upsert_all(db_conn, results)
        print(f"     저장 완료: {metadb.DB_PATH.resolve()}")

        # 기술통계 수집
        print(f"\n[3/4] 기술통계 수집 (동시 {MAX_CONCURRENT}건)...")
        stat_sem = asyncio.Semaphore(MAX_CONCURRENT)
        await asyncio.gather(*[
            _fetch_and_save_stats(conn, db_conn, r, stat_sem)
            for r in ok if r["fields"]
        ])

        # LLM 비즈니스 글로서리 생성 (배치·오프라인 1회성 — 실시간 런타임과 분리)
        print(f"\n[4/4] LLM 비즈니스 글로서리 생성 (Gemini: {GLOSSARY_MODEL})...")
        if os.environ.get("GEMINI_API_KEY"):
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            guideline = _load_guideline()
            print(f"      가이드라인: {'적용 (' + str(GUIDELINE_PATH.name) + ')' if guideline else '없음'}")
            gloss_sem = asyncio.Semaphore(GLOSSARY_CONCURRENT)
            await asyncio.gather(*[
                _generate_datasource_glossary(client, db_conn, r["luid"], r["name"], gloss_sem, guideline)
                for r in ok if r["fields"]
            ])
        else:
            print("      GEMINI_API_KEY 미설정 — 글로서리 생성 단계 스킵")

    # app_log.json 스냅샷 갱신
    _write_app_log(db_conn)
    db_conn.close()

    print(f"\n스냅샷 저장: {OUT_PATH.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())

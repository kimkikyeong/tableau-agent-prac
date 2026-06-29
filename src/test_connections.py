"""
Tableau REST API / VDS 엔드포인트 연결 통합 테스트.
각 단계별 성공/실패를 명확히 출력한다.

실행: uv run python src/test_connections.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import TableauConfig, TableauVDSConnector


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _section(title: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


# ---------------------------------------------------------------------------
# 테스트 1: REST API 인증 + 데이터 소스 목록
# ---------------------------------------------------------------------------

async def test_auth_and_list() -> list[dict] | None:
    _section("TEST 1 · REST API 인증 및 데이터 소스 목록")
    try:
        async with TableauVDSConnector() as conn:
            sources = await conn.get_datasource_metadata()
        _ok(f"PAT 인증 성공")
        _ok(f"데이터 소스 수: {len(sources)}")
        for s in sources[:5]:
            print(f"     [{s.get('id', '?')}] {s.get('name', '?')}")
        return sources
    except Exception as e:
        _fail(f"실패: {e}")
        return None


# ---------------------------------------------------------------------------
# 테스트 2: VDS read-metadata
# ---------------------------------------------------------------------------

async def test_vds_metadata(luid: str, name: str) -> list[dict] | None:
    _section(f"TEST 2 · VDS read-metadata  ({name})")
    try:
        async with TableauVDSConnector() as conn:
            metadata = await conn.get_vds_metadata(luid)
        fields = metadata.get("data", [])
        params = metadata.get("extraData", {}).get("parameters", [])
        _ok(f"메타데이터 조회 성공 | 필드 수: {len(fields)} | 파라미터 수: {len(params)}")

        dims = [f for f in fields if f.get("fieldRole") == "DIMENSION"]
        meas = [f for f in fields if f.get("fieldRole") == "MEASURE"]
        print(f"     DIMENSION({len(dims)}) | MEASURE({len(meas)})")

        visible = [f for f in fields if not f.get("hidden", False)]
        print(f"     조회 가능 필드 (상위 5개):")
        for f in visible[:5]:
            print(
                f"       [{f.get('fieldRole','?'):9s}] "
                f"{f.get('fieldCaption','?'):<30s} "
                f"({f.get('dataType','?')})"
            )
        return visible
    except Exception as e:
        _fail(f"실패: {e}")
        return None


# ---------------------------------------------------------------------------
# 테스트 3: VDS query-datasource
# ---------------------------------------------------------------------------

async def test_vds_query(
    luid: str,
    name: str,
    fields: list[dict],
) -> bool:
    _section(f"TEST 3 · VDS query-datasource  ({name})")

    # 첫 번째 DIMENSION + 첫 번째 MEASURE(SUM)로 간단 쿼리 구성
    dims = [f for f in fields if f.get("fieldRole") == "DIMENSION"]
    meas = [f for f in fields if f.get("fieldRole") == "MEASURE"]

    if not dims or not meas:
        _fail("사용 가능한 DIMENSION 또는 MEASURE 필드 없음 — 쿼리 스킵")
        return False

    dim_caption = dims[0].get("fieldCaption", "")
    meas_caption = meas[0].get("fieldCaption", "")

    query_payload = {
        "fields": [
            {"fieldCaption": dim_caption},
            {"fieldCaption": meas_caption, "function": "SUM"},
        ]
    }
    options = {"rowLimit": 5, "debug": False}

    print(f"     쿼리: [{dim_caption}] + SUM([{meas_caption}])  (최대 5행)")
    try:
        async with TableauVDSConnector() as conn:
            result = await conn.query(luid, query_payload, options)
        data = result.get("data", [])
        _ok(f"쿼리 성공 | 반환 행 수: {len(data)}")
        for row in data:
            print(f"     {row}")
        return True
    except Exception as e:
        _fail(f"실패: {e}")
        return False


# ---------------------------------------------------------------------------
# 환경 변수 사전 점검
# ---------------------------------------------------------------------------

def check_env() -> bool:
    _section("ENV · 환경 변수 점검")
    cfg = TableauConfig.__dataclass_fields__
    required_env = [
        "TABLEAU_VDS_ENDPOINT",
        "TABLEAU_PAT_NAME",
        "TABLEAU_PAT_SECRET",
    ]
    import os
    all_ok = True
    for key in required_env:
        val = os.environ.get(key, "")
        if val:
            masked = val[:6] + "***" if len(val) > 6 else "***"
            _ok(f"{key} = {masked}")
        else:
            _fail(f"{key} 미설정")
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 55)
    print("  Tableau API/VDS 연결 테스트")
    print("=" * 55)

    if not check_env():
        print("\n[STOP]  필수 환경 변수가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    # 1. REST API 인증
    sources = await test_auth_and_list()
    if not sources:
        print("\n[STOP]  REST API 인증 실패 - 이후 테스트 중단")
        sys.exit(1)

    # 2. VDS 메타데이터 (첫 번째 데이터 소스 대상)
    first = sources[0]
    luid, name = first.get("id", ""), first.get("name", "unknown")
    fields = await test_vds_metadata(luid, name)

    # 3. VDS 쿼리
    if fields:
        await test_vds_query(luid, name, fields)

    print(f"\n{'=' * 55}")
    print("  테스트 완료")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    asyncio.run(main())

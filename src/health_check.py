"""
각 인프라 연결 상태를 병렬로 검사하고 src/app_log.json 에 결과를 기록한다.

사용법:
    uv run python src/health_check.py            # 1회 실행
    uv run python src/health_check.py --watch    # 10초 간격 반복
    uv run python src/health_check.py --serve    # HTTP 서버(8000) + watch 동시 실행
                                                 # → http://localhost:8000/monitor.html
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT.parent / ".env")

LOG_PATH = ROOT / "app_log.json"
SUBPROCESS_TIMEOUT = 15.0


def _unwrap_error(e: Exception) -> str:
    """ExceptionGroup(Python 3.11+, asyncio TaskGroup) 내부 예외를 펼쳐 반환한다."""
    if hasattr(e, "exceptions"):
        parts = [str(sub) for sub in e.exceptions]  # type: ignore[attr-defined]
        return " | ".join(parts)[:300]
    return str(e)[:300]


# ────────────────────────────────────────────────────────────────
#  CHECK 1: Tableau VDS API  (PAT 인증 + 데이터 소스 목록 조회)
# ────────────────────────────────────────────────────────────────
async def check_vds_api() -> dict:
    label = "Tableau VDS API"
    start = time.perf_counter()
    try:
        from config import TableauVDSConnector
        async with TableauVDSConnector() as conn:
            sources = await conn.get_datasource_metadata()
        ms = int((time.perf_counter() - start) * 1000)
        return {
            "label": label,
            "status": "connected" if ms < 5000 else "warning",
            "latency_ms": ms,
            "sources_count": len(sources),
        }
    except KeyError as e:
        return {"label": label, "status": "not_configured", "latency_ms": None,
                "error": f"환경 변수 누락: {e}"}
    except Exception as e:
        ms = int((time.perf_counter() - start) * 1000)
        return {"label": label, "status": "disconnected", "latency_ms": ms,
                "error": _unwrap_error(e)}


# ────────────────────────────────────────────────────────────────
#  CHECK 2: ta_mcp  (subprocess 기동 → MCP 초기화 → 툴 목록 확인)
# ────────────────────────────────────────────────────────────────
async def check_ta_mcp() -> dict:
    label = "ta_mcp (Custom VDS)"
    start = time.perf_counter()
    try:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command="uv",
            args=["run", "python", str(ROOT / "tableau_mcp.py")],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=SUBPROCESS_TIMEOUT)
                tools = await session.list_tools()
                ms = int((time.perf_counter() - start) * 1000)
                return {
                    "label": label,
                    "status": "connected",
                    "latency_ms": ms,
                    "tools": [t.name for t in tools.tools],
                }
    except asyncio.TimeoutError:
        ms = int((time.perf_counter() - start) * 1000)
        return {"label": label, "status": "warning", "latency_ms": ms,
                "error": "MCP initialize timeout"}
    except Exception as e:
        ms = int((time.perf_counter() - start) * 1000)
        return {"label": label, "status": "disconnected", "latency_ms": ms,
                "error": _unwrap_error(e)}


# ────────────────────────────────────────────────────────────────
#  CHECK 3: Official Tableau MCP  (npx @tableau/mcp-server@latest)
# ────────────────────────────────────────────────────────────────
async def check_official_mcp() -> dict:
    label = "Official Tableau MCP"

    server   = os.environ.get("TABLEAU_VDS_ENDPOINT", "").rstrip("/")
    site     = os.environ.get("TABLEAU_SITE_ID", "")
    pat_name = os.environ.get("TABLEAU_PAT_NAME", "")
    pat_val  = os.environ.get("TABLEAU_PAT_SECRET", "")

    if not all([server, site, pat_name, pat_val]):
        return {"label": label, "status": "not_configured", "latency_ms": None,
                "note": "Tableau 인증 환경 변수 누락"}

    start = time.perf_counter()
    try:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command="npx",
            args=["-y", "@tableau/mcp-server@latest"],
            env={
                **os.environ,
                "SERVER":    server,
                "SITE_NAME": site,
                "PAT_NAME":  pat_name,
                "PAT_VALUE": pat_val,
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=SUBPROCESS_TIMEOUT)
                tools = await session.list_tools()
                ms = int((time.perf_counter() - start) * 1000)
                return {
                    "label": label,
                    "status": "connected",
                    "latency_ms": ms,
                    "tools": [t.name for t in tools.tools],
                }
    except asyncio.TimeoutError:
        ms = int((time.perf_counter() - start) * 1000)
        return {"label": label, "status": "warning", "latency_ms": ms,
                "error": "MCP initialize timeout"}
    except Exception as e:
        ms = int((time.perf_counter() - start) * 1000)
        return {"label": label, "status": "disconnected", "latency_ms": ms,
                "error": _unwrap_error(e)}


# ────────────────────────────────────────────────────────────────
#  CHECK 4: Guideline Vector DB  (Phase 2 — 미구성)
# ────────────────────────────────────────────────────────────────
async def check_vector_db() -> dict:
    return {
        "label": "Guideline Vector DB",
        "status": "not_configured",
        "latency_ms": None,
        "note": "Phase 2 구현 예정",
    }


# ────────────────────────────────────────────────────────────────
#  RUNNER
# ────────────────────────────────────────────────────────────────
async def run_checks() -> dict:
    """4개 체크를 병렬 실행하고 app_log.json 에 결과를 기록한다."""
    official, ta, vds, vec = await asyncio.gather(
        check_official_mcp(),
        check_ta_mcp(),
        check_vds_api(),
        check_vector_db(),
    )
    log = {
        "updated_at": datetime.now().isoformat(),
        "infrastructure": {
            "official_mcp": official,
            "ta_mcp":       ta,
            "vds_api":      vds,
            "vector_db":    vec,
        },
    }
    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return log


def _print_summary(log: dict) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] 헬스 체크 완료  →  {LOG_PATH}")
    print("─" * 60)
    for item in log["infrastructure"].values():
        status = item["status"].upper()
        ms     = f"{item['latency_ms']}ms" if item.get("latency_ms") is not None else "—"
        extra  = item.get("error") or item.get("note") or ""
        if item.get("tools"):
            extra = f"tools: {item['tools']}"
        extra_str = f"\n    ↳ {extra}" if extra else ""
        print(f"  {item['label']:<28}  [{status:<14}]  {ms}{extra_str}")
    print("─" * 60)


def _start_http_server(port: int = 8000) -> None:
    """백그라운드 스레드에서 HTTP 서버를 기동한다."""
    import http.server
    import threading

    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *_: None  # 접속 로그 숨김

    httpd = http.server.HTTPServer(("", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"모니터 대시보드: http://localhost:{port}/monitor.html")


async def main(watch: bool, serve: bool) -> None:
    if serve:
        import os
        os.chdir(ROOT)  # src/ 기준으로 서빙
        _start_http_server()

    log = await run_checks()
    _print_summary(log)

    if watch:
        print("헬스 체크 시작 (10초 간격, Ctrl+C로 종료)\n")
        while True:
            await asyncio.sleep(10)
            log = await run_checks()
            _print_summary(log)
    elif serve:
        print("서버 실행 중. Ctrl+C로 종료.")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main(
        watch="--watch" in sys.argv,
        serve="--serve" in sys.argv,
    ))

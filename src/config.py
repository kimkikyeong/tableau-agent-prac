"""
Tableau VDS API 커넥터 베이스 모듈.
환경 변수 로드 및 PAT 기반 인증 세션 관리를 담당한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TableauConfig:
    """환경 변수에서 로드된 Tableau 접속 설정."""
    vds_endpoint: str = field(default_factory=lambda: os.environ["TABLEAU_VDS_ENDPOINT"])
    pat_name: str = field(default_factory=lambda: os.environ["TABLEAU_PAT_NAME"])
    pat_secret: str = field(default_factory=lambda: os.environ["TABLEAU_PAT_SECRET"])
    site_id: str = field(default_factory=lambda: os.environ.get("TABLEAU_SITE_ID", ""))
    api_version: str = field(default_factory=lambda: os.environ.get("TABLEAU_API_VERSION", "3.24"))
    timeout: float = field(default_factory=lambda: float(os.environ.get("TABLEAU_TIMEOUT", "30")))


class TableauVDSConnector:
    """
    Tableau VDS REST API와의 인증 세션을 관리하는 베이스 커넥터.

    사용법:
        async with TableauVDSConnector() as conn:
            sources = await conn.get_datasource_metadata()
    """

    def __init__(self, config: TableauConfig | None = None) -> None:
        self._config = config or TableauConfig()
        self._client: httpx.AsyncClient | None = None
        self._auth_token: str | None = None
        self._site_luid: str = ""

    @property
    def _auth_path(self) -> str:
        return f"/api/{self._config.api_version}/auth/signin"

    @property
    def _datasources_path(self) -> str:
        return f"/api/{self._config.api_version}/sites/{self._site_luid}/datasources"

    async def __aenter__(self) -> "TableauVDSConnector":
        self._client = httpx.AsyncClient(
            base_url=self._config.vds_endpoint,
            timeout=self._config.timeout,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        await self._authenticate()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._signout()
        if self._client:
            await self._client.aclose()

    async def _authenticate(self) -> None:
        """PAT(Personal Access Token)으로 Tableau 세션 인증 및 토큰 획득."""
        payload = {
            "credentials": {
                "personalAccessTokenName": self._config.pat_name,
                "personalAccessTokenSecret": self._config.pat_secret,
                "site": {"contentUrl": self._config.site_id},
            }
        }
        response = await self._client.post(self._auth_path, json=payload)
        response.raise_for_status()
        creds = response.json()["credentials"]
        self._auth_token = creds["token"]
        self._site_luid = creds["site"]["id"]
        self._client.headers.update({"x-tableau-auth": self._auth_token})

    async def _signout(self) -> None:
        """세션 종료. 인증 토큰이 없으면 스킵한다."""
        if self._auth_token and self._client:
            await self._client.post(f"/api/{self._config.api_version}/auth/signout")
            self._auth_token = None

    async def get_datasource_metadata(self) -> list[dict[str, Any]]:
        """사용 가능한 데이터 소스의 메타데이터 목록을 반환한다."""
        response = await self._client.get(self._datasources_path)
        response.raise_for_status()
        # Tableau REST API: {"datasources": {"datasource": [...]}}
        return response.json().get("datasources", {}).get("datasource", [])

    async def query(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        특정 VDS 소스에 쿼리 페이로드를 전달하고 결과를 반환한다.

        Args:
            source_id: 대상 데이터 소스 ID
            payload: VDS 쿼리 인자 (필드, 필터, 집계 등)
        """
        response = await self._client.post(
            f"/api/v1/datasources/{source_id}/query",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

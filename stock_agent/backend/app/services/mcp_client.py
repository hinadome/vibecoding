from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

import httpx

from app.config import Settings
from app.models import MCPToolCall

logger = logging.getLogger("uvicorn.error")


class MCPClient:
    """Lightweight MCP JSON-RPC client backed by env-configured server registry."""

    def __init__(self, settings: Settings) -> None:
        """
        Purpose: Initialize with settings carrying MCP server definitions.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `settings` (Settings): Input parameter used by this function.
        Returns:
        - `None`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `__init__(settings=...)`
        """
        self.settings = settings

    def configured_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        Purpose: Return MCP servers mapping from MCP_SERVERS_JSON env configuration.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `Dict[str, Dict[str, Any]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `configured_servers()`
        """
        raw_value = self.settings.mcp_servers_json
        if isinstance(raw_value, dict):
            servers = {
                str(name): cfg
                for name, cfg in raw_value.items()
                if isinstance(cfg, dict) and cfg.get("url")
            }
            if self.settings.app_env == "dev":
                logger.info("MCP configured servers=%s", sorted(servers.keys()))
            return servers

        try:
            raw = json.loads(str(raw_value or "{}"))
            if isinstance(raw, dict):
                servers = {
                    str(name): cfg
                    for name, cfg in raw.items()
                    if isinstance(cfg, dict) and cfg.get("url")
                }
                if self.settings.app_env == "dev":
                    logger.info("MCP configured servers=%s", sorted(servers.keys()))
                return servers
        except json.JSONDecodeError:
            logger.warning(
                "MCP_SERVERS_JSON parse failed raw_value=%s",
                str(raw_value)[:300],
            )
            return {}
        return {}

    async def call_tool(self, call: MCPToolCall) -> str:
        """
        Purpose: Invoke one MCP tool call and return a compact text summary.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `call` (MCPToolCall): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `call_tool(call=...)`
        """
        servers = self.configured_servers()
        cfg = servers.get(call.server)
        if not cfg:
            logger.warning(
                "MCP call skipped server_not_configured server=%s known_servers=%s",
                call.server,
                sorted(servers.keys()),
            )
            return f"MCP server '{call.server}' is not configured."
        started = time.perf_counter()
        url = str(cfg.get("url", "")).strip()
        if self.settings.app_env == "dev":
            logger.info(
                "MCP call request server=%s url=%s tool=%s args_keys=%s",
                call.server,
                url,
                call.tool,
                list(call.arguments.keys()),
            )
        headers = self._headers(cfg)
        payload = {
            "jsonrpc": "2.0",
            "id": "stock-assistant",
            "method": "tools/call",
            "params": {
                "name": call.tool,
                "arguments": call.arguments,
            },
        }

        async with httpx.AsyncClient(timeout=self.settings.outbound_timeout_sec) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if data.get("error"):
            logger.warning(
                "MCP call rpc_error server=%s tool=%s error=%s",
                call.server,
                call.tool,
                str(data.get("error"))[:500],
            )
            return f"MCP error from {call.server}/{call.tool}: {data.get('error')}"

        result = data.get("result")
        if self.settings.app_env == "dev":
            logger.info(
                "MCP call completed server=%s tool=%s elapsed_ms=%d",
                call.server,
                call.tool,
                int((time.perf_counter() - started) * 1000),
            )
        return (
            f"MCP {call.server}/{call.tool}: "
            f"{json.dumps(result, ensure_ascii=False)[:3000]}"
        )

    @staticmethod
    def _headers(cfg: Dict[str, Any]) -> Dict[str, str]:
        """
        Purpose: Build HTTP headers for MCP request from server config.
        Args/Params:
        - `cfg` (Dict[str, Any]): Input parameter used by this function.
        Returns:
        - `Dict[str, str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_headers(cfg=...)`
        """
        headers = {"Content-Type": "application/json"}
        token = cfg.get("bearer_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        custom = cfg.get("headers")
        if isinstance(custom, dict):
            headers.update({str(k): str(v) for k, v in custom.items()})
        return headers

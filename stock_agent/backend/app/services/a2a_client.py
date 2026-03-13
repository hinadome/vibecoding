from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

import httpx

from app.config import Settings
from app.models import A2AAgentCall

logger = logging.getLogger("uvicorn.error")


class A2AClient:
    """Client for calling external agents using simple HTTP-based A2A contracts."""

    def __init__(self, settings: Settings) -> None:
        """
        Purpose: Initialize with settings carrying remote A2A agent definitions.
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

    def configured_agents(self) -> Dict[str, Dict[str, Any]]:
        """
        Purpose: Return agent mapping from A2A_AGENTS_JSON env configuration.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `Dict[str, Dict[str, Any]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `configured_agents()`
        """
        raw_value = self.settings.a2a_agents_json
        if isinstance(raw_value, dict):
            agents = {
                str(name): cfg
                for name, cfg in raw_value.items()
                if isinstance(cfg, dict) and cfg.get("url")
            }
            if self.settings.app_env == "dev":
                logger.info("A2A configured agents=%s", sorted(agents.keys()))
            return agents

        try:
            raw = json.loads(str(raw_value or "{}"))
            if isinstance(raw, dict):
                agents = {
                    str(name): cfg
                    for name, cfg in raw.items()
                    if isinstance(cfg, dict) and cfg.get("url")
                }
                if self.settings.app_env == "dev":
                    logger.info("A2A configured agents=%s", sorted(agents.keys()))
                return agents
        except json.JSONDecodeError:
            logger.warning(
                "A2A_AGENTS_JSON parse failed raw_value=%s",
                str(raw_value)[:300],
            )
            return {}
        return {}

    async def invoke(self, call: A2AAgentCall) -> str:
        """
        Purpose: Invoke one remote agent task and return summarized response text.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `call` (A2AAgentCall): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `invoke(call=...)`
        """
        agents = self.configured_agents()
        cfg = agents.get(call.agent)
        if not cfg:
            logger.warning(
                "A2A invoke skipped agent_not_configured agent=%s known_agents=%s",
                call.agent,
                sorted(agents.keys()),
            )
            return f"A2A agent '{call.agent}' is not configured."
        started = time.perf_counter()
        url = str(cfg.get("url", "")).strip()
        if self.settings.app_env == "dev":
            logger.info(
                "A2A invoke request agent=%s url=%s task_chars=%d context_keys=%s",
                call.agent,
                url,
                len(call.task),
                list(call.context.keys()),
            )
        headers = self._headers(cfg)
        payload = {
            "task": call.task,
            "context": call.context,
        }

        async with httpx.AsyncClient(timeout=self.settings.outbound_timeout_sec) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        if isinstance(data, dict) and "result" in data:
            content = data["result"]
        else:
            content = data
        if self.settings.app_env == "dev":
            logger.info(
                "A2A invoke completed agent=%s elapsed_ms=%d",
                call.agent,
                int((time.perf_counter() - started) * 1000),
            )

        return f"A2A {call.agent}: {json.dumps(content, ensure_ascii=False)[:3000]}"

    @staticmethod
    def _headers(cfg: Dict[str, Any]) -> Dict[str, str]:
        """
        Purpose: Build HTTP headers for A2A call from agent config.
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

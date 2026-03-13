from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, List

import httpx

from app.config import Settings
from app.services.dev_log_sink import rotate_file_if_oversized

logger = logging.getLogger("uvicorn.error")
DEBUG_PAYLOAD_FILE = Path(__file__).resolve().parents[2] / "debug_payload.txt"


class OpenAICompatibleClient:
    def __init__(self, settings: Settings) -> None:
        """
        Purpose: Initialize client with OpenAI-compatible endpoint settings.
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

    @property
    def is_enabled(self) -> bool:
        """
        Purpose: Check whether required LLM credentials and base URL are configured.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `bool`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `is_enabled()`
        """
        return bool(self.settings.openai_api_key and self.settings.openai_base_url)

    async def chat_markdown(self, system_prompt: str, user_prompt: str) -> str:
        """
        Purpose: Request a full markdown completion in non-streaming mode.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `system_prompt` (str): Input parameter used by this function.
        - `user_prompt` (str): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `chat_markdown(system_prompt=..., user_prompt=...)`
        """
        if not self.is_enabled:
            raise RuntimeError("OpenAI-compatible endpoint is not configured")
        started = time.perf_counter()
        if self.settings.app_env == "dev":
            logger.info(
                "LLM chat request model=%s base_url=%s prompt_chars=%d",
                self.settings.openai_chat_model,
                self.settings.openai_base_url,
                len(user_prompt),
            )

        payload = {
            "model": self.settings.openai_chat_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        request_url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        self._append_debug_payload(
            event="chat_markdown",
            endpoint=request_url,
            payload=payload,
        )

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                request_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        if self.settings.app_env == "dev":
            logger.info(
                "LLM chat response status=%s elapsed_ms=%d",
                200,
                int((time.perf_counter() - started) * 1000),
            )

        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

    async def chat_markdown_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncIterator[str]:
        """
        Purpose: Stream markdown deltas from chat completions and yield text chunks.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `system_prompt` (str): Input parameter used by this function.
        - `user_prompt` (str): Input parameter used by this function.
        Returns:
        - `AsyncIterator[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `chat_markdown_stream(system_prompt=..., user_prompt=...)`
        """
        if not self.is_enabled:
            raise RuntimeError("OpenAI-compatible endpoint is not configured")
        started = time.perf_counter()
        streamed_chars = 0
        if self.settings.app_env == "dev":
            logger.info(
                "LLM stream request model=%s base_url=%s prompt_chars=%d",
                self.settings.openai_chat_model,
                self.settings.openai_base_url,
                len(user_prompt),
            )

        payload = {
            "model": self.settings.openai_chat_model,
            "temperature": 0.2,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        request_url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        self._append_debug_payload(
            event="chat_markdown_stream",
            endpoint=request_url,
            payload=payload,
        )

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                request_url,
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload_line = line[5:].strip()
                    if payload_line == "[DONE]":
                        break
                    try:
                        data = json.loads(payload_line)
                    except json.JSONDecodeError:
                        continue
                    chunk = (
                        data.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if chunk:
                        streamed_chars += len(chunk)
                        yield chunk
        if self.settings.app_env == "dev":
            logger.info(
                "LLM stream completed chars=%d elapsed_ms=%d",
                streamed_chars,
                int((time.perf_counter() - started) * 1000),
            )

    async def embed(self, text: str) -> List[float]:
        """
        Purpose: Generate embedding vector for retrieval augmentation.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `text` (str): Input parameter used by this function.
        Returns:
        - `List[float]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `embed(text=...)`
        """
        if not self.is_enabled:
            return []
        started = time.perf_counter()
        if self.settings.app_env == "dev":
            logger.info(
                "Embedding request model=%s base_url=%s input_chars=%d",
                self.settings.openai_embedding_model,
                self.settings.openai_base_url,
                len(text),
            )

        payload = {
            "model": self.settings.openai_embedding_model,
            "input": text,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        request_url = f"{self.settings.openai_base_url.rstrip('/')}/embeddings"
        self._append_debug_payload(
            event="embedding",
            endpoint=request_url,
            payload=payload,
        )

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                request_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        vector = data.get("data", [{}])[0].get("embedding", [])
        if self.settings.app_env == "dev":
            logger.info(
                "Embedding response vector_dims=%d elapsed_ms=%d",
                len(vector),
                int((time.perf_counter() - started) * 1000),
            )

        return vector

    def _append_debug_payload(
        self,
        event: str,
        endpoint: str,
        payload: dict,
    ) -> None:
        """
        Purpose: Append outbound LLM payload metadata to debug file in dev environment.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `event` (str): Input parameter used by this function.
        - `endpoint` (str): Input parameter used by this function.
        - `payload` (dict): Input parameter used by this function.
        Returns:
        - `None`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_append_debug_payload(event=..., endpoint=..., payload=...)`
        """
        if self.settings.app_env != "dev":
            return
        try:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "endpoint": endpoint,
                "payload": payload,
            }
            DEBUG_PAYLOAD_FILE.parent.mkdir(parents=True, exist_ok=True)
            rotate_file_if_oversized(DEBUG_PAYLOAD_FILE)
            with DEBUG_PAYLOAD_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False))
                fh.write("\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to append debug payload log: %s", str(exc))

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("uvicorn.error")
AB_METRICS_FILE = Path(__file__).resolve().parents[2] / "ab_metrics.log"
MAX_DEV_LOG_BYTES = 50 * 1024 * 1024
MAX_DEV_LOG_BACKUPS = 3


def rotate_file_if_oversized(
    log_file: Path,
    max_bytes: int = MAX_DEV_LOG_BYTES,
    backup_count: int = MAX_DEV_LOG_BACKUPS,
) -> None:
    """
    Purpose: Rotate a log file when size reaches threshold, keeping a few backups.
    Args/Params:
    - `log_file` (Path): Input parameter used by this function.
    - `max_bytes` (int): Input parameter used by this function.
    - `backup_count` (int): Input parameter used by this function.
    Returns:
    - `None`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `rotate_file_if_oversized(log_file=..., max_bytes=..., backup_count=...)`
    """
    if not log_file.exists():
        return
    if log_file.stat().st_size < max_bytes:
        return

    oldest = log_file.with_name(f"{log_file.name}.{backup_count}")
    if oldest.exists():
        oldest.unlink()

    for idx in range(backup_count - 1, 0, -1):
        src = log_file.with_name(f"{log_file.name}.{idx}")
        dst = log_file.with_name(f"{log_file.name}.{idx + 1}")
        if src.exists():
            src.replace(dst)

    log_file.replace(log_file.with_name(f"{log_file.name}.1"))


def append_ab_metric(app_env: str, event: str, payload: dict[str, Any]) -> None:
    """
    Purpose: Append structured A/B metric records to a local sink in dev environment.
    Args/Params:
    - `app_env` (str): Input parameter used by this function.
    - `event` (str): Input parameter used by this function.
    - `payload` (dict[str, Any]): Input parameter used by this function.
    Returns:
    - `None`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `append_ab_metric(app_env=..., event=..., payload=...)`
    """
    if app_env != "dev":
        return

    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        AB_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        rotate_file_if_oversized(AB_METRICS_FILE)
        with AB_METRICS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to append AB metric log: %s", str(exc))

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Any

import requests

from src.utils.config import PROJECT_ROOT
from src.utils.io import sha256_file, utc_now_iso, write_json_exclusive


class AlphaVantageClient:
    """Small cached client that never puts the API key in a saved URL."""

    base_url = "https://www.alphavantage.co/query"

    def __init__(self, cache_dir: Path | None = None, timeout: int = 45):
        self.api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ALPHAVANTAGE_API_KEY is not set. Configure it in the process "
                "environment; do not place it in source code."
            )
        self.cache_dir = cache_dir or (
            PROJECT_ROOT / "data" / "raw" / "alphavantage"
        )
        self.timeout = timeout

    @staticmethod
    def _cache_id(params: dict[str, Any]) -> str:
        safe = {k: params[k] for k in sorted(params) if k.lower() != "apikey"}
        return hashlib.sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()[:20]

    def get_json(
        self,
        *,
        function: str,
        max_attempts: int = 5,
        **params: Any,
    ) -> dict[str, Any]:
        safe_params = {"function": function, **params}
        cache_id = self._cache_id(safe_params)
        path = self.cache_dir / f"{function.lower()}-{cache_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for attempt in range(max_attempts):
            try:
                response = requests.get(
                    self.base_url,
                    params={**safe_params, "apikey": self.api_key},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                # Requests exceptions can contain the fully prepared URL, including
                # its query-string credential, so never propagate their text.
                raise RuntimeError(
                    "Alpha Vantage request failed; URL and credential were redacted."
                ) from None
            except requests.JSONDecodeError as exc:
                raise RuntimeError("Alpha Vantage returned invalid JSON.") from exc
            rate_limited = "Note" in payload or "Information" in payload
            if rate_limited and attempt < max_attempts - 1:
                time.sleep((2**attempt) + random.random())
                continue
            if "Error Message" in payload:
                raise ValueError(payload["Error Message"])
            if rate_limited:
                raise RuntimeError("Alpha Vantage returned an information/rate-limit response")

            with path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            write_json_exclusive(
                path.with_suffix(".metadata.json"),
                {
                    "provider": "Alpha Vantage",
                    "function": function,
                    "parameters": params,
                    "download_time_utc": utc_now_iso(),
                    "source_timezone": "provider-specific",
                    "record_count": _record_count(payload),
                    "file_size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                },
            )
            return payload
        raise AssertionError("unreachable")

    def news_sentiment(
        self,
        *,
        tickers: str | None = None,
        topics: str | None = None,
        time_from: str,
        time_to: str,
        limit: int = 1000,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "time_from": time_from,
            "time_to": time_to,
            "sort": "EARLIEST",
            "limit": limit,
        }
        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics
        return self.get_json(function="NEWS_SENTIMENT", **params)


def _record_count(payload: dict[str, Any]) -> int | None:
    for key in ("feed", "data"):
        if isinstance(payload.get(key), list):
            return len(payload[key])
    return None

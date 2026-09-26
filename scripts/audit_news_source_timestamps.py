from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

import pandas as pd
import requests

from src.utils.config import PROJECT_ROOT


META_PATTERNS = (
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|date|parsely-pub-date)["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:published_time|datePublished|date|parsely-pub-date)["\']',
    r'<time[^>]+datetime=["\']([^"\']+)',
)


def _json_dates(value: object) -> list[str]:
    dates: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"datePublished", "dateCreated", "uploadDate"} and isinstance(item, str):
                dates.append(item)
            else:
                dates.extend(_json_dates(item))
    elif isinstance(value, list):
        for item in value:
            dates.extend(_json_dates(item))
    return dates


def _extract_dates(html: str) -> list[str]:
    values: list[str] = []
    for pattern in META_PATTERNS:
        values.extend(re.findall(pattern, html, flags=re.IGNORECASE))
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            values.extend(_json_dates(json.loads(unescape(block.strip()))))
        except (json.JSONDecodeError, TypeError):
            continue
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _audit(row: dict[str, object], timeout: float) -> dict[str, object]:
    base = {
        "candidate_id": row["candidate_id"],
        "article_id": row["article_id"],
        "ticker": row["ticker"],
        "provider_time_utc": row["time_published_utc"],
        "source_url": row["url"],
    }
    try:
        response = requests.get(
            str(row["url"]),
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 academic timestamp audit"},
        )
        response.raise_for_status()
        raw_dates = _extract_dates(response.text)
        parsed = pd.to_datetime(pd.Series(raw_dates, dtype="object"), utc=True, errors="coerce")
        parsed = parsed.dropna()
        source_time = parsed.min() if not parsed.empty else pd.NaT
        provider_time = pd.Timestamp(row["time_published_utc"])
        difference = (
            None
            if pd.isna(source_time)
            else float((provider_time - source_time).total_seconds())
        )
        status = "source_metadata_found" if not pd.isna(source_time) else "no_source_timestamp_metadata"
        return {
            **base,
            "http_status": response.status_code,
            "final_url": response.url,
            "source_time_utc": source_time,
            "provider_minus_source_seconds": difference,
            "audit_status": status,
            "raw_timestamp_candidates": "|".join(raw_dates[:10]),
            "error": "",
        }
    except requests.RequestException as exc:
        return {
            **base,
            "http_status": getattr(exc.response, "status_code", None),
            "final_url": getattr(exc.response, "url", None),
            "source_time_utc": pd.NaT,
            "provider_minus_source_seconds": None,
            "audit_status": "source_fetch_failed",
            "raw_timestamp_candidates": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract source-page publication metadata for selected Alpha Vantage news"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    candidates = pd.read_csv(
        PROJECT_ROOT / "data" / "processed" / "news_event_candidates.csv"
    )
    if args.limit:
        candidates = candidates.head(args.limit)
    records = candidates.to_dict("records")
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_audit, row, args.timeout): row for row in records}
        for future in as_completed(futures):
            result = future.result()
            rows.append(result)
            print(f"{result['candidate_id']}: {result['audit_status']}")
    audit = pd.DataFrame(rows).sort_values("candidate_id")
    output = PROJECT_ROOT / "data" / "processed" / "news_source_timestamp_audit.csv"
    audit.to_csv(output, index=False)
    counts = audit["audit_status"].value_counts()
    print(f"Wrote {len(audit)} source checks to {output}\n{counts.to_string()}")


if __name__ == "__main__":
    main()

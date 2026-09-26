from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
import pandas as pd


NEWS_COLUMNS = [
    "article_id",
    "provider",
    "time_published_utc",
    "timestamp_precision",
    "timestamp_quality",
    "first_publication_verified",
    "source_publication_time_utc",
    "validated_event_time_utc",
    "timestamp_validation_status",
    "alpha_minus_source_seconds",
    "title",
    "summary",
    "source",
    "source_domain",
    "url",
    "canonical_url",
    "authors_json",
    "category_within_source",
    "topics_json",
    "overall_sentiment_score",
    "overall_sentiment_label",
    "ticker",
    "ticker_relevance_score",
    "ticker_sentiment_score",
    "ticker_sentiment_label",
    "query_ticker",
    "query_topic",
    "duplicate_story_group",
    "eligible_as_unscheduled_event",
    "retrieved_utc",
    "raw_file",
]


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_alpha_vantage_time(value: Any) -> tuple[pd.Timestamp, str]:
    """Parse the provider publication field as UTC and report its resolution."""
    text = str(value or "").strip()
    digits = re.sub(r"[^0-9]", "", text)
    precision = "unknown"
    if len(digits) >= 14:
        precision = "second"
    elif len(digits) >= 12:
        precision = "minute"
    timestamp = pd.to_datetime(text, format="%Y%m%dT%H%M%S", utc=True, errors="coerce")
    if pd.isna(timestamp):
        timestamp = pd.to_datetime(text, format="%Y%m%dT%H%M", utc=True, errors="coerce")
    if pd.isna(timestamp):
        timestamp = pd.to_datetime(text, utc=True, errors="coerce")
    return timestamp, precision


def _article_id(article: dict[str, Any]) -> str:
    canonical_url = canonicalize_url(article.get("url"))
    identity = "|".join(
        [
            canonical_url,
            str(article.get("time_published", "")).strip(),
            str(article.get("source", "")).strip(),
            str(article.get("title", "")).strip(),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def canonicalize_url(value: Any) -> str:
    """Remove common tracking parameters while retaining content-defining queries."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    tracking_names = {
        "fbclid", "gclid", "mc_cid", "mc_eid", "gaa_at", "gaa_n", "gaa_ts", "gaa_sig",
    }
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in tracking_names and not key.lower().startswith("utm_")
    ]
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", netloc, path, urlencode(sorted(query)), ""))


def _story_group(title: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _metadata_for(path: Path) -> dict[str, Any]:
    metadata_path = path.with_suffix(".metadata.json")
    if not metadata_path.exists():
        return {}
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def normalize_news_payload(
    payload: dict[str, Any],
    *,
    raw_file: str = "",
    query_ticker: str | None = None,
    query_topic: str | None = None,
    retrieved_utc: str | None = None,
) -> pd.DataFrame:
    """Flatten Alpha Vantage articles to one row per article-ticker pair."""
    rows: list[dict[str, Any]] = []
    for article in payload.get("feed", []):
        timestamp, precision = parse_alpha_vantage_time(article.get("time_published"))
        topics = article.get("topics") if isinstance(article.get("topics"), list) else []
        ticker_items = (
            article.get("ticker_sentiment")
            if isinstance(article.get("ticker_sentiment"), list)
            else []
        )
        if not ticker_items:
            ticker_items = [{"ticker": query_ticker}]
        common = {
            "article_id": _article_id(article),
            "provider": "Alpha Vantage",
            "time_published_utc": timestamp,
            "timestamp_precision": precision,
            # This is a publisher/provider timestamp until source-level checks prove otherwise.
            "timestamp_quality": "provider_publication_time_unverified",
            "first_publication_verified": False,
            "source_publication_time_utc": pd.NaT,
            "validated_event_time_utc": pd.NaT,
            "timestamp_validation_status": "not_checked",
            "alpha_minus_source_seconds": None,
            "title": article.get("title"),
            "summary": article.get("summary"),
            "source": article.get("source"),
            "source_domain": article.get("source_domain"),
            "url": article.get("url"),
            "canonical_url": canonicalize_url(article.get("url")),
            "authors_json": json.dumps(article.get("authors") or [], ensure_ascii=False),
            "category_within_source": article.get("category_within_source"),
            "topics_json": json.dumps(topics, ensure_ascii=False, sort_keys=True),
            "overall_sentiment_score": _number(article.get("overall_sentiment_score")),
            "overall_sentiment_label": article.get("overall_sentiment_label"),
            "query_ticker": query_ticker,
            "query_topic": query_topic,
            "duplicate_story_group": _story_group(article.get("title")),
            # A story becomes eligible only after manual/source timestamp validation.
            "eligible_as_unscheduled_event": False,
            "retrieved_utc": retrieved_utc,
            "raw_file": raw_file,
        }
        for item in ticker_items:
            rows.append(
                {
                    **common,
                    "ticker": item.get("ticker"),
                    "ticker_relevance_score": _number(item.get("relevance_score")),
                    "ticker_sentiment_score": _number(item.get("ticker_sentiment_score")),
                    "ticker_sentiment_label": item.get("ticker_sentiment_label"),
                }
            )
    return pd.DataFrame(rows, columns=NEWS_COLUMNS)


def normalize_cached_news(
    paths: Iterable[str | Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize cached payloads and return a query-coverage audit table."""
    frames: list[pd.DataFrame] = []
    query_rows: list[dict[str, Any]] = []
    for value in paths:
        path = Path(value)
        if path.name.endswith(".metadata.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        metadata = _metadata_for(path)
        parameters = metadata.get("parameters") or {}
        query_ticker = parameters.get("tickers")
        query_topic = parameters.get("topics")
        frames.append(
            normalize_news_payload(
                payload,
                raw_file=str(path),
                query_ticker=query_ticker,
                query_topic=query_topic,
                retrieved_utc=metadata.get("download_time_utc"),
            )
        )
        feed_count = len(payload.get("feed", []))
        limit = int(parameters.get("limit", 1000))
        query_rows.append(
            {
                "raw_file": str(path),
                "query_ticker": query_ticker,
                "query_topic": query_topic,
                "time_from": parameters.get("time_from"),
                "time_to": parameters.get("time_to"),
                "limit": limit,
                "article_count": feed_count,
                "possible_truncation": feed_count >= limit,
                "download_time_utc": metadata.get("download_time_utc"),
            }
        )
    news = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=NEWS_COLUMNS)
    if not news.empty:
        news["time_published_utc"] = pd.to_datetime(
            news["time_published_utc"], utc=True, errors="coerce"
        )
        news["_ticker_key"] = news["ticker"].fillna("<NO_TICKER>")
        group_keys = ["article_id", "_ticker_key"]
        for column in ("query_ticker", "query_topic", "raw_file"):
            news[column] = news.groupby(group_keys, dropna=False)[column].transform(
                lambda values: "|".join(sorted(set(values.dropna().astype(str)))) or None
            )
        news = news.drop_duplicates(group_keys, keep="first").drop(columns="_ticker_key")
        news = news.sort_values(
            ["time_published_utc", "article_id", "ticker"], na_position="last"
        )
    return news.reset_index(drop=True), pd.DataFrame(query_rows)


def apply_timestamp_validations(
    news: pd.DataFrame, validations: dict[str, dict[str, Any]]
) -> pd.DataFrame:
    """Attach source-level timestamp checks without overwriting provider fields."""
    result = news.copy()
    for column, default in (
        ("source_publication_time_utc", pd.NaT),
        ("validated_event_time_utc", pd.NaT),
        ("timestamp_validation_status", "not_checked"),
        ("alpha_minus_source_seconds", np.nan),
    ):
        if column not in result:
            result[column] = default
    for column in ("source_publication_time_utc", "validated_event_time_utc"):
        result[column] = pd.to_datetime(result[column], utc=True, errors="coerce")
    for article_id, metadata in validations.items():
        mask = result["article_id"].eq(article_id)
        if not mask.any():
            continue
        source_value = metadata.get("source_time_utc")
        source_time = pd.NaT if source_value is None else pd.Timestamp(source_value)
        status = str(metadata.get("validation_status", "not_checked"))
        result.loc[mask, "timestamp_validation_status"] = status
        if pd.notna(source_time):
            if source_time.tzinfo is None:
                raise ValueError(f"source timestamp for {article_id} must be timezone-aware")
            source_time = source_time.tz_convert("UTC")
            result.loc[mask, "source_publication_time_utc"] = source_time
            alpha_time = pd.to_datetime(
                result.loc[mask, "time_published_utc"], utc=True, errors="coerce"
            )
            result.loc[mask, "alpha_minus_source_seconds"] = (
                alpha_time - source_time
            ).dt.total_seconds()
        verified = status in {"verified_match", "source_time_verified_alpha_mismatch"}
        result.loc[mask, "first_publication_verified"] = verified
        result.loc[mask, "eligible_as_unscheduled_event"] = verified
        if verified:
            result.loc[mask, "validated_event_time_utc"] = source_time
            result.loc[mask, "timestamp_quality"] = "source_publication_time_verified"
    for column in ("source_publication_time_utc", "validated_event_time_utc"):
        result[column] = pd.to_datetime(result[column], utc=True, errors="coerce")
    return result

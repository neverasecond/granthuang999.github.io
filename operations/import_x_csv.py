#!/usr/bin/env python3
"""Import a weekly X analytics CSV into the private operations endpoint."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


OPS_ENDPOINT = os.environ.get(
    "OPS_ENDPOINT", "https://www.790427.xyz/api/ops/weekly-input"
)

FIELDS = {
    "followers": (
        "followers",
        "follower count",
        "followers at week end",
        "total followers",
    ),
    "postsPublished": (
        "posts",
        "posts published",
        "post count",
        "tweets",
    ),
    "impressions": ("impressions",),
    "profileVisits": (
        "profile visits",
        "profile clicks",
        "profile_clicks",
        "user profile clicks",
        "user_profile_clicks",
    ),
    "linkClicks": (
        "link clicks",
        "url clicks",
        "url_clicks",
        "url_click",
    ),
    "bookmarks": ("bookmarks",),
    "replies": ("replies",),
    "reposts": (
        "reposts",
        "retweets",
        "shares",
    ),
}


def normalize_name(value: str) -> str:
    text = value.replace("\ufeff", "").strip().lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", "."}:
        return 0.0
    number = float(cleaned)
    return -number if negative else number


def canonical_field(name: str) -> str | None:
    normalized = normalize_name(name)
    for field, aliases in FIELDS.items():
        if normalized in aliases:
            return field
    padded = f" {normalized} "
    for field, aliases in FIELDS.items():
        if any(f" {alias} " in padded for alias in aliases):
            return field
    return None


def read_csv_text(args: argparse.Namespace) -> str:
    sources = [bool(args.csv_path), bool(args.csv_data), args.stdin]
    if sum(1 for item in sources if item) != 1:
        raise SystemExit("Provide exactly one of --csv-path, --csv-data, or --stdin.")
    if args.csv_path:
        return Path(args.csv_path).read_text(encoding="utf-8-sig")
    if args.csv_data:
        return args.csv_data
    return sys.stdin.read()


def rows_from_text(csv_text: str) -> list[dict[str, str]]:
    sample = csv_text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
    return [
        {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
        for row in reader
    ]


def parse_metric_value_rows(rows: list[dict[str, str]]) -> dict[str, float]:
    totals = {field: 0.0 for field in FIELDS}
    if not rows:
        return totals
    headers = [normalize_name(name) for name in rows[0]]
    metric_key = next((name for name in rows[0] if normalize_name(name) in {"metric", "指标", "name"}), "")
    value_key = next((name for name in rows[0] if normalize_name(name) in {"value", "值", "total"}), "")
    if not metric_key or not value_key:
        return totals

    for row in rows:
        field = canonical_field(row.get(metric_key, ""))
        if field:
            totals[field] += parse_number(row.get(value_key))
    return totals


def parse_table_rows(rows: list[dict[str, str]]) -> dict[str, float]:
    totals = {field: 0.0 for field in FIELDS}
    matched_headers = {
        header: canonical_field(header)
        for header in rows[0].keys()
    } if rows else {}
    matched_headers = {key: value for key, value in matched_headers.items() if value}
    for row in rows:
        for header, field in matched_headers.items():
            totals[field] += parse_number(row.get(header))
    if not totals["postsPublished"] and rows:
        totals["postsPublished"] = float(len(rows))
    return totals


def parse_x_csv(csv_text: str) -> dict[str, float]:
    rows = rows_from_text(csv_text)
    totals = parse_metric_value_rows(rows)
    if any(totals.values()):
        return totals
    return parse_table_rows(rows)


def parse_time_split(value: str) -> tuple[float, float]:
    try:
        creation, interaction = [float(part.strip()) for part in value.split(",", 1)]
    except ValueError as exc:
        raise SystemExit("--time-split must look like 20,20") from exc
    if creation < 0 or interaction < 0:
        raise SystemExit("--time-split values must be non-negative.")
    return creation, interaction


def build_payload(args: argparse.Namespace) -> dict[str, int | float | str]:
    totals = parse_x_csv(read_csv_text(args))
    creation, interaction = parse_time_split(args.time_split)
    return {
        "weekEnding": args.week_ending,
        "followers": int(round(totals["followers"])),
        "postsPublished": int(round(totals["postsPublished"])),
        "impressions": int(round(totals["impressions"])),
        "profileVisits": int(round(totals["profileVisits"])),
        "linkClicks": int(round(totals["linkClicks"])),
        "bookmarks": int(round(totals["bookmarks"])),
        "replies": int(round(totals["replies"])),
        "reposts": int(round(totals["reposts"])),
        "creationHours": creation,
        "interactionHours": interaction,
    }


def post_payload(payload: dict[str, int | float | str]) -> dict:
    token = os.environ.get("NEWSLETTER_SEND_TOKEN", "").strip()
    if not token:
        raise SystemExit("NEWSLETTER_SEND_TOKEN is required unless --dry-run is used.")
    request = urllib.request.Request(
        OPS_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import weekly X analytics from CSV.")
    parser.add_argument("--week-ending", required=True, help="Week ending date, YYYY-MM-DD")
    parser.add_argument("--time-split", default="20,20", help="Creation and interaction hours, for example 20,20")
    parser.add_argument("--csv-path", help="Path to a CSV file")
    parser.add_argument("--csv-data", help="Raw CSV content")
    parser.add_argument("--stdin", action="store_true", help="Read CSV content from stdin")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print payload without sending")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(args)
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    result = post_payload(payload)
    print(json.dumps({"stored": bool(result.get("stored")), "weekEnding": result.get("weekEnding")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

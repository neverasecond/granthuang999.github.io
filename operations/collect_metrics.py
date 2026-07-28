#!/usr/bin/env python3
"""Collect private daily operating metrics and send scheduled reports.

Only aggregate values are transmitted. No subscriber email, visitor identifier,
article body, cookie, IP address, or X account record is collected.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
SITE_URL = os.environ.get("SITE_URL", "https://www.790427.xyz").rstrip("/")
GA4_PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "369092012")
SEARCH_CONSOLE_SITE = os.environ.get(
    "SEARCH_CONSOLE_SITE", "https://www.790427.xyz/"
)
OPS_ENDPOINT = os.environ.get(
    "OPS_ENDPOINT", f"{SITE_URL}/api/ops"
).rstrip("/")
USER_AGENT = "DailyOperationsMetrics/1.0 (+https://www.790427.xyz/)"
ENGAGEMENT_EVENTS = (
    "scroll_50",
    "scroll_90",
    "article_share",
    "related_article_click",
    "outbound_x_click",
    "newsletter_submit",
    "newsletter_confirm",
)
ARTICLE_EVENTS = (
    "scroll_50",
    "scroll_90",
    "article_share",
    "related_article_click",
    "outbound_x_click",
)


@dataclass
class Metric:
    source: str
    metric: str
    value: float
    dimension: str = ""
    metadata: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "metric": self.metric,
            "dimension": self.dimension,
            "value": self.value,
            "metadata": self.metadata or {},
        }


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def google_access_token(credentials_json: str) -> str:
    credentials = json.loads(credentials_json)
    now = int(time.time())
    signing_input = ".".join(
        [
            b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode()),
            b64url(
                json.dumps(
                    {
                        "iss": credentials["client_email"],
                        "scope": " ".join(
                            [
                                "https://www.googleapis.com/auth/analytics.readonly",
                                "https://www.googleapis.com/auth/webmasters.readonly",
                            ]
                        ),
                        "aud": "https://oauth2.googleapis.com/token",
                        "iat": now,
                        "exp": now + 3600,
                    },
                    separators=(",", ":"),
                ).encode()
            ),
        ]
    ).encode("ascii")

    key_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as key_file:
            key_file.write(credentials["private_key"])
            key_path = key_file.name
        signature = subprocess.check_output(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input,
        )
    finally:
        if key_path:
            os.unlink(key_path)

    assertion = signing_input.decode("ascii") + "." + b64url(signature)
    payload = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
    ).encode()
    response = request_json(
        "https://oauth2.googleapis.com/token",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return str(response["access_token"])


def request_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    json_body: Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> Any:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(
        url, data=data, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        message = ""
        try:
            error_payload = json.loads(body)
            error_data = error_payload.get("error", error_payload)
            if isinstance(error_data, dict):
                message = str(error_data.get("message") or error_data.get("status") or "")
        except json.JSONDecodeError:
            pass
        host = urllib.parse.urlsplit(url).hostname or "remote API"
        detail = f": {message[:240]}" if message else ""
        raise RuntimeError(f"HTTP {error.code} from {host}{detail}") from error
    return json.loads(raw.decode("utf-8")) if raw else {}


def authorized_json(
    path: str, *, method: str = "GET", json_body: Any | None = None
) -> Any:
    return request_json(
        f"{OPS_ENDPOINT}/{path.lstrip('/')}",
        method=method,
        json_body=json_body,
        headers={"Authorization": f"Bearer {require_env('NEWSLETTER_SEND_TOKEN')}"},
    )


def ga4_report(token: str, body: dict[str, Any]) -> dict[str, Any]:
    return request_json(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY_ID}:runReport",
        method="POST",
        json_body=body,
        headers={"Authorization": f"Bearer {token}"},
    )


def collect_ga4(token: str, metric_date: dt.date) -> list[Metric]:
    date_text = metric_date.isoformat()
    metrics: list[Metric] = []
    summary = ga4_report(
        token,
        {
            "dateRanges": [{"startDate": date_text, "endDate": date_text}],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "newUsers"},
                {"name": "sessions"},
                {"name": "engagedSessions"},
                {"name": "screenPageViews"},
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"},
            ],
        },
    )
    headers = [item["name"] for item in summary.get("metricHeaders", [])]
    rows = summary.get("rows", [])
    values = rows[0].get("metricValues", []) if rows else []
    for name, raw in zip(headers, values):
        metrics.append(Metric("ga4", name, float(raw.get("value") or 0)))

    returning = ga4_report(
        token,
        {
            "dateRanges": [{"startDate": date_text, "endDate": date_text}],
            "dimensions": [{"name": "newVsReturning"}],
            "metrics": [{"name": "activeUsers"}],
        },
    )
    for row in returning.get("rows", []):
        dimension = row["dimensionValues"][0].get("value", "unknown")
        value = float(row["metricValues"][0].get("value") or 0)
        metrics.append(Metric("ga4", "activeUsersByType", value, dimension))

    top_pages = ga4_report(
        token,
        {
            "dateRanges": [{"startDate": date_text, "endDate": date_text}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [
                {"name": "screenPageViews"},
                {"name": "activeUsers"},
                {"name": "averageSessionDuration"},
            ],
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
            "limit": "20",
        },
    )
    page_headers = [item["name"] for item in top_pages.get("metricHeaders", [])]
    for row in top_pages.get("rows", []):
        path = row["dimensionValues"][0].get("value", "")[:500]
        for name, raw in zip(page_headers, row.get("metricValues", [])):
            metrics.append(Metric("ga4_page", name, float(raw.get("value") or 0), path))
    return metrics


def rate(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 4) if denominator > 0 else 0.0


def change_rate(current: float, baseline: float) -> float:
    return round(((current - baseline) / baseline) * 100, 4) if baseline > 0 else 0.0


def collect_ga4_window(token: str, metric_date: dt.date, days: int) -> list[Metric]:
    end_date = metric_date
    start_date = metric_date - dt.timedelta(days=days - 1)
    date_range = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
    }
    metadata = {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}
    summary_source = f"ga4_{days}d"
    engagement_source = f"ga4_engagement_{days}d"
    metrics: list[Metric] = []

    summary = ga4_report(
        token,
        {
            "dateRanges": [date_range],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "engagedSessions"},
                {"name": "screenPageViews"},
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"},
            ],
        },
    )
    headers = [item["name"] for item in summary.get("metricHeaders", [])]
    rows = summary.get("rows", [])
    values = rows[0].get("metricValues", []) if rows else []
    for name, raw in zip(headers, values):
        metrics.append(
            Metric(summary_source, name, float(raw.get("value") or 0), metadata=metadata)
        )

    event_report = ga4_report(
        token,
        {
            "dateRanges": [date_range],
            "dimensions": [{"name": "eventName"}],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "eventName",
                    "inListFilter": {"values": list(ENGAGEMENT_EVENTS)},
                }
            },
            "limit": "50",
        },
    )
    event_counts = {event_name: 0.0 for event_name in ENGAGEMENT_EVENTS}
    for row in event_report.get("rows", []):
        event_name = row["dimensionValues"][0].get("value", "")
        if event_name in event_counts:
            event_counts[event_name] = float(row["metricValues"][0].get("value") or 0)

    post_pages = ga4_report(
        token,
        {
            "dateRanges": [date_range],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "screenPageViews"}],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "pagePath",
                    "stringFilter": {
                        "matchType": "BEGINS_WITH",
                        "value": "/post/",
                        "caseSensitive": False,
                    },
                }
            },
            "limit": "10000",
        },
    )
    post_page_views = sum(
        float(row["metricValues"][0].get("value") or 0)
        for row in post_pages.get("rows", [])
    )
    metrics.append(
        Metric(engagement_source, "postPageViews", post_page_views, metadata=metadata)
    )
    for event_name, value in event_counts.items():
        metrics.append(
            Metric(engagement_source, event_name, value, metadata=metadata)
        )
    metrics.extend(
        [
            Metric(
                engagement_source,
                "completion50Rate",
                rate(event_counts["scroll_50"], post_page_views),
                metadata=metadata,
            ),
            Metric(
                engagement_source,
                "completion90Rate",
                rate(event_counts["scroll_90"], post_page_views),
                metadata=metadata,
            ),
            Metric(
                engagement_source,
                "shareRate",
                rate(event_counts["article_share"], post_page_views),
                metadata=metadata,
            ),
            Metric(
                engagement_source,
                "relatedClickRate",
                rate(event_counts["related_article_click"], post_page_views),
                metadata=metadata,
            ),
            Metric(
                engagement_source,
                "outboundXRate",
                rate(event_counts["outbound_x_click"], post_page_views),
                metadata=metadata,
            ),
            Metric(
                engagement_source,
                "newsletterConfirmRate",
                rate(event_counts["newsletter_confirm"], event_counts["newsletter_submit"]),
                metadata=metadata,
            ),
        ]
    )

    if days == 28:
        page_events = ga4_report(
            token,
            {
                "dateRanges": [date_range],
                "dimensions": [{"name": "eventName"}, {"name": "pagePath"}],
                "metrics": [{"name": "eventCount"}],
                "dimensionFilter": {
                    "andGroup": {
                        "expressions": [
                            {
                                "filter": {
                                    "fieldName": "eventName",
                                    "inListFilter": {"values": list(ARTICLE_EVENTS)},
                                }
                            },
                            {
                                "filter": {
                                    "fieldName": "pagePath",
                                    "stringFilter": {
                                        "matchType": "BEGINS_WITH",
                                        "value": "/post/",
                                        "caseSensitive": False,
                                    },
                                }
                            },
                        ]
                    }
                },
                "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
                "limit": "100",
            },
        )
        for row in page_events.get("rows", []):
            event_name = row["dimensionValues"][0].get("value", "")[:120]
            page_path = row["dimensionValues"][1].get("value", "")[:500]
            value = float(row["metricValues"][0].get("value") or 0)
            metrics.append(
                Metric(
                    "ga4_event_page_28d",
                    event_name,
                    value,
                    page_path,
                    metadata,
                )
            )
    return metrics


def collect_search_console(token: str, metric_date: dt.date) -> list[Metric]:
    # Search Console is delayed. Use the latest stable 28-day window ending 3 days ago.
    end_date = metric_date - dt.timedelta(days=2)
    start_date = end_date - dt.timedelta(days=27)
    endpoint = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        f"{urllib.parse.quote(SEARCH_CONSOLE_SITE, safe='')}/searchAnalytics/query"
    )
    headers = {"Authorization": f"Bearer {token}"}
    base = {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}
    overall = request_json(endpoint, method="POST", json_body=base, headers=headers)
    metrics: list[Metric] = []
    rows = overall.get("rows", [])
    row = rows[0] if rows else {}
    for name in ("clicks", "impressions", "ctr", "position"):
        metrics.append(
            Metric(
                "search_console_28d",
                name,
                float(row.get(name) or 0),
                metadata={"startDate": start_date.isoformat(), "endDate": end_date.isoformat()},
            )
        )

    for dimension in ("query", "page"):
        result = request_json(
            endpoint,
            method="POST",
            json_body={**base, "dimensions": [dimension], "rowLimit": 20},
            headers=headers,
        )
        for item in result.get("rows", []):
            key = str((item.get("keys") or [""])[0])[:500]
            for name in ("clicks", "impressions", "ctr", "position"):
                metrics.append(
                    Metric(f"search_console_{dimension}_28d", name, float(item.get(name) or 0), key)
                )
    return metrics


def clarity_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").rstrip("%")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def collect_clarity() -> list[Metric]:
    result = request_json(
        "https://www.clarity.ms/export-data/api/v1/project-live-insights"
        "?numOfDays=1&dimension1=URL",
        headers={"Authorization": f"Bearer {require_env('CLARITY_API_TOKEN')}"},
    )
    metrics: list[Metric] = []
    for entry in result if isinstance(result, list) else []:
        metric_name = str(entry.get("metricName") or entry.get("name") or "unknown")[:120]
        information = entry.get("information") or entry.get("data") or []
        if not isinstance(information, list):
            information = [information]
        for item in information:
            if not isinstance(item, dict):
                continue
            dimension = str(
                item.get("Url")
                or item.get("URL")
                or item.get("url")
                or item.get("dimension")
                or "all"
            )[:500]
            for field_name, raw_value in item.items():
                number = clarity_number(raw_value)
                if number is not None:
                    metrics.append(
                        Metric(
                            "clarity",
                            f"{metric_name}.{str(field_name)[:80]}",
                            number,
                            dimension,
                        )
                    )
    # Keep the private ingestion request comfortably below the Worker batch limit.
    return metrics[:200]


def collect_newsletter(metric_date: dt.date) -> list[Metric]:
    result = authorized_json(f"newsletter-metrics?metricDate={metric_date.isoformat()}")
    return [
        Metric("newsletter", key, float(value))
        for key, value in result.items()
        if isinstance(value, (int, float))
    ]


def collect_weekly_input() -> list[Metric]:
    result = authorized_json("weekly-input")
    week_ending = str(result.get("weekEnding") or "")
    if not week_ending:
        return []
    x_fields = (
        "followers", "postsPublished", "impressions", "profileVisits",
        "linkClicks", "bookmarks", "replies", "reposts",
    )
    time_fields = ("creationHours", "interactionHours")
    metrics = [
        Metric("x_csv", field, float(result.get(field) or 0), metadata={"weekEnding": week_ending})
        for field in x_fields
    ]
    metrics.extend(
        Metric("operations_time", field, float(result.get(field) or 0), metadata={"weekEnding": week_ending})
        for field in time_fields
    )
    return metrics


def collect_clarity_review() -> list[Metric]:
    result = authorized_json("clarity-review")
    week_ending = str(result.get("weekEnding") or "")
    reviews = result.get("reviews") if isinstance(result, dict) else []
    if not week_ending or not isinstance(reviews, list):
        return []
    metrics: list[Metric] = []
    for review in reviews[:20]:
        if not isinstance(review, dict):
            continue
        page_path = str(review.get("pagePath") or "sitewide")[:500]
        recordings = float(review.get("recordingsReviewed") or 0)
        metrics.append(
            Metric(
                "clarity_review",
                "recordingsReviewed",
                recordings,
                page_path,
                {
                    "weekEnding": week_ending,
                    "heatmapFinding": str(review.get("heatmapFinding") or "")[:1500],
                    "recordingFinding": str(review.get("recordingFinding") or "")[:1500],
                    "actionDecision": str(review.get("actionDecision") or "")[:1500],
                },
            )
        )
    return metrics


def check_url(url: str) -> tuple[int, float, str]:
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = int(response.status)
        error = ""
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        error = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - health errors are aggregated for alerting.
        status = 0
        error = type(exc).__name__
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    return status, elapsed_ms, error


def collect_health() -> tuple[list[Metric], list[str]]:
    urls = {
        "home": f"{SITE_URL}/",
        "rss": f"{SITE_URL}/rss.xml",
        "sitemap": f"{SITE_URL}/sitemap.xml",
        "subscribe": f"{SITE_URL}/subscribe.html",
    }
    metrics: list[Metric] = []
    failures: list[str] = []
    for name, url in urls.items():
        status, latency, error = check_url(url)
        metrics.extend(
            [
                Metric("health", "httpStatus", status, name, {"url": url}),
                Metric("health", "latencyMs", latency, name, {"url": url}),
            ]
        )
        if status < 200 or status >= 400:
            failures.append(f"{name}: {status or error}")

    try:
        worker_health = authorized_json("health")
        ok = worker_health.get("ok") is True and worker_health.get("database") == "ok"
        metrics.append(Metric("health", "workerOk", 1 if ok else 0, "newsletter_worker"))
        if not ok:
            failures.append("newsletter_worker: database check failed")
    except Exception as exc:  # noqa: BLE001
        metrics.append(Metric("health", "workerOk", 0, "newsletter_worker"))
        failures.append(f"newsletter_worker: {type(exc).__name__}")
    return metrics, failures


def find_metric(metrics: list[Metric], source: str, name: str, dimension: str = "") -> float:
    for item in metrics:
        if item.source == source and item.metric == name and item.dimension == dimension:
            return item.value
    return 0.0


def find_metrics(metrics: list[Metric], source: str, name: str) -> list[Metric]:
    return [item for item in metrics if item.source == source and item.metric == name]


def find_first_metric(metrics: list[Metric], candidates: tuple[tuple[str, str], ...]) -> float:
    for source, name in candidates:
        value = find_metric(metrics, source, name)
        if value:
            return value
    return 0.0


def fmt_number(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def build_report(
    metrics: list[Metric],
    metric_date: dt.date,
    report_mode: str,
    failures: list[str],
    source_errors: list[str],
) -> tuple[str, str, str]:
    active = find_metric(metrics, "ga4", "activeUsers")
    views = find_metric(metrics, "ga4", "screenPageViews")
    sessions = find_metric(metrics, "ga4", "sessions")
    returning = find_metric(metrics, "ga4", "activeUsersByType", "returning")
    clicks = find_metric(metrics, "search_console_28d", "clicks")
    impressions = find_metric(metrics, "search_console_28d", "impressions")
    ctr = find_metric(metrics, "search_console_28d", "ctr") * 100
    active_subscribers = find_metric(metrics, "newsletter", "activeSubscribers")
    pending_subscribers = find_metric(metrics, "newsletter", "pendingSubscribers")
    new_subscribers = find_metric(metrics, "newsletter", "createdYesterday")
    confirmed = find_metric(metrics, "newsletter", "confirmedYesterday")
    unsubscribed = find_metric(metrics, "newsletter", "unsubscribedYesterday")
    x_source_label = "固定 CSV 自动导入"
    x_followers = find_metric(metrics, "x_csv", "followers")
    x_posts = find_first_metric(
        metrics,
        (("x_csv", "postsPublished"),),
    )
    x_impressions = find_first_metric(
        metrics,
        (("x_csv", "impressions"),),
    )
    x_bookmarks = find_first_metric(
        metrics,
        (("x_csv", "bookmarks"),),
    )
    x_profile_clicks = find_first_metric(
        metrics,
        (("x_csv", "profileVisits"),),
    )
    x_link_clicks = find_first_metric(
        metrics,
        (("x_csv", "linkClicks"),),
    )
    x_replies = find_first_metric(
        metrics,
        (("x_csv", "replies"),),
    )
    x_reposts = find_first_metric(
        metrics,
        (("x_csv", "reposts"),),
    )
    creation_hours = find_metric(metrics, "operations_time", "creationHours")
    interaction_hours = find_metric(metrics, "operations_time", "interactionHours")
    active_7d = find_metric(metrics, "ga4_7d", "activeUsers")
    active_28d = find_metric(metrics, "ga4_28d", "activeUsers")
    views_7d = find_metric(metrics, "ga4_7d", "screenPageViews")
    views_28d = find_metric(metrics, "ga4_28d", "screenPageViews")
    views_daily_7d = views_7d / 7
    views_daily_28d = views_28d / 28
    views_pace_change = change_rate(views_daily_7d, views_daily_28d)
    completion_7d = find_metric(metrics, "ga4_engagement_7d", "completion90Rate")
    completion_28d = find_metric(metrics, "ga4_engagement_28d", "completion90Rate")
    share_rate_7d = find_metric(metrics, "ga4_engagement_7d", "shareRate")
    share_rate_28d = find_metric(metrics, "ga4_engagement_28d", "shareRate")
    related_rate_7d = find_metric(metrics, "ga4_engagement_7d", "relatedClickRate")
    related_rate_28d = find_metric(metrics, "ga4_engagement_28d", "relatedClickRate")
    x_outbound_rate_7d = find_metric(metrics, "ga4_engagement_7d", "outboundXRate")
    x_outbound_rate_28d = find_metric(metrics, "ga4_engagement_28d", "outboundXRate")
    newsletter_created_7d = find_metric(metrics, "newsletter", "created7d")
    newsletter_confirmed_7d = find_metric(metrics, "newsletter", "confirmed7d")
    newsletter_created_28d = find_metric(metrics, "newsletter", "created28d")
    newsletter_confirmed_28d = find_metric(metrics, "newsletter", "confirmed28d")
    newsletter_rate_7d = rate(newsletter_confirmed_7d, newsletter_created_7d)
    newsletter_rate_28d = rate(newsletter_confirmed_28d, newsletter_created_28d)
    clarity_api_metrics = [item for item in metrics if item.source == "clarity"]
    clarity_api_count = len(clarity_api_metrics)
    clarity_api_lines = []
    for item in clarity_api_metrics[:8]:
        clarity_api_lines.append(
            f"- {item.dimension}：{item.metric} = {fmt_number(item.value, 2)}"
        )
    clarity_api_text = "\n".join(clarity_api_lines) or "- Clarity API 暂无可用数据"

    report_titles = {
        "daily": "每日运营基线",
        "weekly": "每周运营报告",
        "monthly": "月度运营报告",
    }
    prefix = "异常告警" if failures or source_errors else report_titles.get(report_mode, "运营报告")
    subject = f"{prefix}｜人到中年｜{metric_date.isoformat()}"
    issues = failures + source_errors
    issue_lines = "\n".join(f"- {item}" for item in issues) or "- 无"
    text = f"""{subject}

网站（昨日）
- 活跃用户：{fmt_number(active)}
- 会话：{fmt_number(sessions)}
- 页面浏览：{fmt_number(views)}
- 回访活跃用户：{fmt_number(returning)}

网站趋势与内容质量
- 7日 / 28日活跃用户：{fmt_number(active_7d)} / {fmt_number(active_28d)}
- 7日 / 28日页面浏览：{fmt_number(views_7d)} / {fmt_number(views_28d)}
- 7日 / 28日日均页面浏览：{fmt_number(views_daily_7d, 1)} / {fmt_number(views_daily_28d, 1)}（近7日节奏 {views_pace_change:+.2f}%）
- 90%阅读完成率：{fmt_number(completion_7d, 2)}% / {fmt_number(completion_28d, 2)}%
- 分享点击率：{fmt_number(share_rate_7d, 2)}% / {fmt_number(share_rate_28d, 2)}%
- 相关阅读点击率：{fmt_number(related_rate_7d, 2)}% / {fmt_number(related_rate_28d, 2)}%
- 网站到X点击率：{fmt_number(x_outbound_rate_7d, 2)}% / {fmt_number(x_outbound_rate_28d, 2)}%

Google 搜索（稳定的最近28天窗口）
- 点击：{fmt_number(clicks)}
- 展示：{fmt_number(impressions)}
- CTR：{fmt_number(ctr, 2)}%

邮件订阅
- 有效订阅：{fmt_number(active_subscribers)}
- 待确认：{fmt_number(pending_subscribers)}
- 昨日新增：{fmt_number(new_subscribers)}
- 昨日确认：{fmt_number(confirmed)}
- 昨日退订：{fmt_number(unsubscribed)}
- 7日确认转化：{fmt_number(newsletter_confirmed_7d)} / {fmt_number(newsletter_created_7d)}（{fmt_number(newsletter_rate_7d, 2)}%）
- 28日确认转化：{fmt_number(newsletter_confirmed_28d)} / {fmt_number(newsletter_created_28d)}（{fmt_number(newsletter_rate_28d, 2)}%）

Clarity（API 自动采集，最近 1 天）
- API 指标行：{fmt_number(clarity_api_count)}
{clarity_api_text}

X（{x_source_label}）
- 新增关注/关注数：{fmt_number(x_followers)}
- 跟踪/发布数：{fmt_number(x_posts)}
- 展示：{fmt_number(x_impressions)}
- 个人资料点击：{fmt_number(x_profile_clicks)}
- 链接点击：{fmt_number(x_link_clicks)}
- 收藏：{fmt_number(x_bookmarks)}
- 回复：{fmt_number(x_replies)}
- 转发：{fmt_number(x_reposts)}

时间投入（最近一周）
- 创作：{fmt_number(creation_hours, 1)} 小时
- 互动：{fmt_number(interaction_hours, 1)} 小时

健康与采集问题
{issue_lines}

说明：GA4、Search Console、Clarity 走 API 自动采集；X 使用每周 CSV 导入后的汇总数据。AdSense 批准前不采集收入。
"""
    escaped_issues = "".join(f"<li>{html.escape(item)}</li>" for item in issues) or "<li>无</li>"
    report_html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.65;color:#24292f;max-width:720px;margin:0 auto">
      <h1 style="font-size:22px">{html.escape(prefix)}</h1>
      <p style="color:#57606a">统计日期：{metric_date.isoformat()}</p>
      <h2 style="font-size:17px">网站（昨日）</h2>
      <ul><li>活跃用户：{fmt_number(active)}</li><li>会话：{fmt_number(sessions)}</li><li>页面浏览：{fmt_number(views)}</li><li>回访活跃用户：{fmt_number(returning)}</li></ul>
      <h2 style="font-size:17px">网站趋势与内容质量</h2>
      <ul><li>7日 / 28日活跃用户：{fmt_number(active_7d)} / {fmt_number(active_28d)}</li><li>7日 / 28日页面浏览：{fmt_number(views_7d)} / {fmt_number(views_28d)}</li><li>7日 / 28日日均页面浏览：{fmt_number(views_daily_7d, 1)} / {fmt_number(views_daily_28d, 1)}（近7日节奏 {views_pace_change:+.2f}%）</li><li>90%阅读完成率：{fmt_number(completion_7d, 2)}% / {fmt_number(completion_28d, 2)}%</li><li>分享点击率：{fmt_number(share_rate_7d, 2)}% / {fmt_number(share_rate_28d, 2)}%</li><li>相关阅读点击率：{fmt_number(related_rate_7d, 2)}% / {fmt_number(related_rate_28d, 2)}%</li><li>网站到X点击率：{fmt_number(x_outbound_rate_7d, 2)}% / {fmt_number(x_outbound_rate_28d, 2)}%</li></ul>
      <h2 style="font-size:17px">Google 搜索（稳定的最近28天窗口）</h2>
      <ul><li>点击：{fmt_number(clicks)}</li><li>展示：{fmt_number(impressions)}</li><li>CTR：{fmt_number(ctr, 2)}%</li></ul>
      <h2 style="font-size:17px">邮件订阅</h2>
      <ul><li>有效订阅：{fmt_number(active_subscribers)}</li><li>待确认：{fmt_number(pending_subscribers)}</li><li>昨日新增：{fmt_number(new_subscribers)}</li><li>昨日确认：{fmt_number(confirmed)}</li><li>昨日退订：{fmt_number(unsubscribed)}</li><li>7日确认转化：{fmt_number(newsletter_confirmed_7d)} / {fmt_number(newsletter_created_7d)}（{fmt_number(newsletter_rate_7d, 2)}%）</li><li>28日确认转化：{fmt_number(newsletter_confirmed_28d)} / {fmt_number(newsletter_created_28d)}（{fmt_number(newsletter_rate_28d, 2)}%）</li></ul>
      <h2 style="font-size:17px">Clarity（API 自动采集，最近 1 天）</h2>
      <ul><li>API 指标行：{fmt_number(clarity_api_count)}</li></ul>
      <div style="font-size:14px;color:#57606a">{html.escape(clarity_api_text).replace(chr(10), '<br>')}</div>
      <h2 style="font-size:17px">X（{html.escape(x_source_label)}）</h2>
      <ul><li>新增关注/关注数：{fmt_number(x_followers)}</li><li>跟踪/发布数：{fmt_number(x_posts)}</li><li>展示：{fmt_number(x_impressions)}</li><li>个人资料点击：{fmt_number(x_profile_clicks)}</li><li>链接点击：{fmt_number(x_link_clicks)}</li><li>收藏：{fmt_number(x_bookmarks)}</li><li>回复：{fmt_number(x_replies)}</li><li>转发：{fmt_number(x_reposts)}</li></ul>
      <h2 style="font-size:17px">时间投入（最近一周）</h2>
      <ul><li>创作：{fmt_number(creation_hours, 1)} 小时</li><li>互动：{fmt_number(interaction_hours, 1)} 小时</li></ul>
      <h2 style="font-size:17px">健康与采集问题</h2><ul>{escaped_issues}</ul>
      <p style="font-size:13px;color:#57606a">GA4、Search Console、Clarity 走 API 自动采集；X 使用每周 CSV 导入后的汇总数据。AdSense 批准前不采集收入。</p>
    </div>
    """
    return subject, report_html, text


def resolve_report_mode(requested: str, now: dt.datetime, has_failures: bool) -> str:
    if requested != "auto":
        return requested
    if now.day == 1:
        return "monthly"
    if now.weekday() == 0:
        return "weekly"
    if has_failures:
        return "alert"
    return "none"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-mode", choices=("auto", "daily", "weekly", "monthly"), default="auto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = dt.datetime.now(SHANGHAI)
    metric_date = now.date() - dt.timedelta(days=1)
    run_id = os.environ.get("GITHUB_RUN_ID") or str(uuid.uuid4())
    credentials_json = require_env("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_JSON")
    source_errors: list[str] = []
    metrics: list[Metric] = []

    health_metrics, health_failures = collect_health()
    metrics.extend(health_metrics)

    token = google_access_token(credentials_json)
    collectors = (
        ("ga4", lambda: collect_ga4(token, metric_date)),
        ("ga4_7d", lambda: collect_ga4_window(token, metric_date, 7)),
        ("ga4_28d", lambda: collect_ga4_window(token, metric_date, 28)),
        ("search_console", lambda: collect_search_console(token, metric_date)),
        ("clarity", collect_clarity),
        ("newsletter", lambda: collect_newsletter(metric_date)),
        ("x_csv", collect_weekly_input),
    )
    for source, collector in collectors:
        try:
            metrics.extend(collector())
        except Exception as exc:  # noqa: BLE001 - one source must not erase other sources.
            detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            source_errors.append(f"{source}: {detail}")
            print(f"Collector failed: {source}: {detail}")

    report_mode = resolve_report_mode(
        args.report_mode, now, bool(health_failures or source_errors)
    )
    payload = {
        "runId": str(run_id),
        "metricDate": metric_date.isoformat(),
        "reportMode": report_mode,
        "status": "partial" if source_errors else "success",
        "errors": source_errors + health_failures,
        "metrics": [item.as_payload() for item in metrics],
    }

    if args.dry_run:
        print(
            json.dumps(
                {
                    "metricDate": payload["metricDate"],
                    "reportMode": report_mode,
                    "metricCount": len(metrics),
                    "sources": sorted({item.source for item in metrics}),
                    "errors": payload["errors"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if len(metrics) > 480:
        source_errors.append(f"metric_limit: truncated {len(metrics) - 480} rows")
        metrics = metrics[:480]
        payload["status"] = "partial"
        payload["errors"] = source_errors + health_failures
        payload["metrics"] = [item.as_payload() for item in metrics]

    store_result = authorized_json("metrics", method="POST", json_body=payload)
    if report_mode != "none":
        subject, report_html, report_text = build_report(
            metrics, metric_date, report_mode, health_failures, source_errors
        )
        authorized_json(
            "report",
            method="POST",
            json_body={"subject": subject, "html": report_html, "text": report_text},
        )

    print(
        json.dumps(
            {
                "metricDate": payload["metricDate"],
                "reportMode": report_mode,
                "metricCount": len(metrics),
                "storedMetricCount": int(store_result.get("stored") or 0),
                "sources": sorted({item.source for item in metrics}),
                "errorCount": len(payload["errors"]),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not health_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

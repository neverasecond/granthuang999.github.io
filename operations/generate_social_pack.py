#!/usr/bin/env python3
"""Generate a manual social distribution pack for one published Gmeek article.

The script intentionally does not publish anything. It reads local Gmeek
metadata and backup Markdown, then writes platform-ready drafts for manual
review and posting.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from textwrap import shorten


ROOT = Path(__file__).resolve().parents[1]
BLOG_BASE = ROOT / "blogBase.json"
BACKUP_DIR = ROOT / "backup"
DEFAULT_OUTPUT_DIR = ROOT / "content-packages"

X_LIMIT = 280
X_SAFE_LIMIT = 260

CATEGORY_HASHTAGS = {
    "人生修行": ["#midlife", "#reading", "#life"],
    "赚钱投资": ["#investing", "#personalfinance", "#riskmanagement"],
    "技术辅助": ["#AI", "#automation", "#productivity"],
}

CATEGORY_ENGLISH = {
    "人生修行": "midlife reflection",
    "赚钱投资": "personal finance and investing",
    "技术辅助": "practical technology and AI",
}


def load_posts() -> dict[str, dict]:
    try:
        data = json.loads(BLOG_BASE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Missing {BLOG_BASE}")
    posts = data.get("postListJson", {})
    return {key: value for key, value in posts.items() if key.startswith("P") and isinstance(value, dict)}


def issue_key(issue: str | int) -> str:
    text = str(issue).strip()
    return text if text.upper().startswith("P") else f"P{text.lstrip('#')}"


def sanitize_title(title: str) -> str:
    return re.sub(r"[<>:/\\|?*\"]|[\0-\31]", "-", title)


def find_backup(post: dict) -> Path:
    exact = BACKUP_DIR / f"{sanitize_title(post['postTitle'])}.md"
    if exact.exists():
        return exact

    candidates = sorted(BACKUP_DIR.glob("*.md"))
    normalized_title = normalize(post["postTitle"])
    for candidate in candidates:
        if normalize(candidate.stem) == normalized_title:
            return candidate

    raise SystemExit(f"Could not find backup Markdown for: {post['postTitle']}")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def strip_markdown(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^[>\-*+]\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？!?])\s*", text)
    return [item.strip() for item in raw if item.strip()]


def split_paragraphs(markdown: str) -> list[str]:
    paragraphs = []
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block or block.startswith("##{"):
            continue
        plain = strip_markdown(block)
        if len(plain) >= 24:
            paragraphs.append(plain)
    return paragraphs


def choose_points(markdown: str, max_points: int = 6) -> list[str]:
    paragraphs = split_paragraphs(markdown)
    points = []
    seen = set()
    for paragraph in paragraphs:
        if paragraph in seen:
            continue
        seen.add(paragraph)
        if 28 <= len(paragraph) <= 220:
            points.append(paragraph)
        elif len(paragraph) > 220:
            sentences = split_sentences(paragraph)
            if sentences:
                points.append(shorten(sentences[0], width=180, placeholder="..."))
        if len(points) >= max_points:
            break
    return points


def compact(text: str, width: int) -> str:
    return shorten(re.sub(r"\s+", " ", text).strip(), width=width, placeholder="...")


def tags_for(post: dict) -> list[str]:
    tags = []
    for label in post.get("labels", []):
        tags.extend(CATEGORY_HASHTAGS.get(label, []))
    if not tags:
        tags = ["#midlife", "#newsletter"]
    deduped = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped[:4]


def x_single(post: dict, points: list[str]) -> str:
    url = post["postUrl"]
    title = post["postTitle"]
    hook = points[0] if points else post.get("description", "")
    tags = " ".join(tags_for(post)[:2])
    budget = X_LIMIT - len(url) - len(title) - len(tags) - 10
    body = compact(hook, max(50, budget))
    return f"{title}\n\n{body}\n\n{url}\n{tags}".strip()


def x_thread(post: dict, points: list[str]) -> list[str]:
    url = post["postUrl"]
    title = post["postTitle"]
    thread = []
    first_point = points[0] if points else post.get("description", "")
    intro_budget = X_LIMIT - len(title) - len(url) - 6
    intro = f"{title}\n\n{compact(first_point, max(40, intro_budget))}\n\n{url}"
    thread.append(intro if len(intro) <= X_LIMIT else compact(intro, X_LIMIT))
    for index, point in enumerate(points[1:7], start=2):
        prefix = f"{index}/ "
        thread.append(prefix + compact(point, X_SAFE_LIMIT - len(prefix)))
    if len(thread) > 1:
        thread[-1] = compact(thread[-1] + "\n\n" + " ".join(tags_for(post)[:3]), X_LIMIT)
    return thread


def linkedin_cn(post: dict, points: list[str]) -> str:
    title = post["postTitle"]
    url = post["postUrl"]
    body_points = "\n".join(f"- {compact(point, 160)}" for point in points[:5])
    category = post.get("contentCategory") or "个人记录"
    return (
        f"{title}\n\n"
        f"这篇文章放在「{category}」里，我想讨论的不是一个孤立技巧，而是一个中年以后更常见的问题："
        f"{compact(post.get('description', ''), 180)}\n\n"
        f"{body_points}\n\n"
        f"完整文章：{url}\n\n"
        f"{' '.join(tags_for(post))}"
    ).strip()


def linkedin_en(post: dict, points: list[str]) -> str:
    category = CATEGORY_ENGLISH.get(post.get("contentCategory", ""), "midlife notes")
    url = post["postUrl"]
    translated_title = english_angle(post["postTitle"], post.get("contentCategory", ""))
    bullet_items = []
    for point in points:
        item = english_point(point)
        if item not in bullet_items:
            bullet_items.append(item)
        if len(bullet_items) >= 4:
            break
    bullets = "\n".join(f"- {item}" for item in bullet_items)
    return (
        f"{translated_title}\n\n"
        f"A short note from my Chinese site about {category}. The full piece is in Chinese, "
        f"but the core question travels well: how do we make calmer decisions when midlife gives us more duties, "
        f"less spare attention, and higher downside costs?\n\n"
        f"{bullets}\n\n"
        f"Full article: {url}\n\n"
        f"#midlife #decisionmaking #personalfinance"
    ).strip()


def english_angle(title: str, category: str) -> str:
    if category == "赚钱投资":
        return "Investing should be a result, not the center of family life"
    if category == "技术辅助":
        return "Using technology as practical support, not as another source of noise"
    if "红楼" in title:
        return "Reading a classic again as a midlife survival manual"
    if "坛经" in title or "惠能" in title:
        return "A midlife note on identity, circumstance, and inner practice"
    return "A midlife note from a Chinese personal site"


def english_point(point: str) -> str:
    patterns = [
        ("投资", "Investing is only useful when it serves a real-life responsibility."),
        ("家庭", "Family decisions need boundaries before they need more tactics."),
        ("风险", "Risk is not abstract; it shows up as stress, timing pressure, and relationship cost."),
        ("中年", "Midlife makes trade-offs more visible, and therefore more honest."),
        ("技术", "Technology should solve a concrete problem, not become another trend to chase."),
        ("关系", "The hardest part is often not the method, but the relationship around it."),
    ]
    for needle, sentence in patterns:
        if needle in point:
            return sentence
    return "The useful question is not what sounds right, but what still works under pressure."


def bluesky(post: dict, points: list[str]) -> str:
    text = f"{english_angle(post['postTitle'], post.get('contentCategory', ''))}\n\n{post['postUrl']}"
    return compact(text, 300)


def mastodon(post: dict, points: list[str]) -> str:
    first = points[0] if points else post.get("description", "")
    text = (
        f"{english_angle(post['postTitle'], post.get('contentCategory', ''))}\n\n"
        f"{english_point(first)}\n\n"
        f"{post['postUrl']}\n\n"
        f"#midlife #writing"
    )
    return compact(text, 500)


def title_options(post: dict, points: list[str]) -> list[str]:
    title = post["postTitle"]
    options = [title]
    category = post.get("contentCategory", "")
    if category == "赚钱投资":
        options.extend([
            "普通家庭先有财务秩序，再谈投资收益",
            "别把投资理财变成家庭生活的目标",
        ])
    elif category == "技术辅助":
        options.extend([
            "中年人用技术，应该先解决真实问题",
            "不追工具，把 AI 用回生活现场",
        ])
    else:
        options.extend([
            "人到中年，重新理解自己的处境",
            "不是寻找答案，而是重新训练判断力",
        ])
    return options[:3]


def build_pack(post: dict, markdown: str) -> str:
    points = choose_points(markdown)
    issue_number = post.get("postSourceUrl", "").rstrip("/").split("/")[-1]
    lines = []
    lines.append(f"# Social Pack: #{issue_number} {post['postTitle']}")
    lines.append("")
    lines.append(f"- URL: {post['postUrl']}")
    lines.append(f"- Category: {post.get('contentCategory') or ','.join(post.get('labels', []))}")
    lines.append(f"- Date: {post.get('createdDate', '')}")
    lines.append("")
    lines.append("## Title Options")
    for option in title_options(post, points):
        lines.append(f"- {option}")
    lines.append("")
    lines.append("## X Single Post")
    single = x_single(post, points)
    lines.append(f"<!-- {len(single)} chars -->")
    lines.append(single)
    lines.append("")
    lines.append("## X Thread")
    for item in x_thread(post, points):
        lines.append(f"<!-- {len(item)} chars -->")
        lines.append(item)
        lines.append("")
    lines.append("## LinkedIn Chinese")
    lines.append(linkedin_cn(post, points))
    lines.append("")
    lines.append("## LinkedIn English")
    lines.append(linkedin_en(post, points))
    lines.append("")
    lines.append("## Bluesky English")
    lines.append(bluesky(post, points))
    lines.append("")
    lines.append("## Mastodon English")
    lines.append(mastodon(post, points))
    lines.append("")
    lines.append("## Manual Checklist")
    lines.extend([
        "- Read once before posting; remove anything too absolute.",
        "- Add one fresh personal sentence before posting to LinkedIn.",
        "- Confirm the article URL opens correctly.",
        "- Avoid posting identical text to every platform.",
        "- Record the final platform URLs if you want later analytics.",
    ])
    return "\n".join(lines).strip() + "\n"


def post_issue_number(key: str, post: dict) -> str:
    source_issue = post.get("postSourceUrl", "").rstrip("/").split("/")[-1]
    if source_issue.isdigit():
        return source_issue
    return key.lstrip("P")


def post_slug(post: dict) -> str:
    url_tail = post.get("postUrl", "").rstrip("/").split("/")[-1]
    slug = url_tail.removesuffix(".html")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    return slug or "article"


def default_output_path(key: str, post: dict) -> Path:
    issue_number = post_issue_number(key, post)
    return DEFAULT_OUTPUT_DIR / f"social-pack-P{issue_number}-{post_slug(post)}.md"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def select_post(posts: dict[str, dict], args: argparse.Namespace) -> tuple[str, dict]:
    if args.latest:
        key, post = max(posts.items(), key=lambda item: item[1].get("createdAt", 0))
        return key, post
    key = issue_key(args.issue)
    if key not in posts:
        raise SystemExit(f"Issue {key} is not in published postListJson.")
    return key, posts[key]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate manual social drafts for a published Gmeek article.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", help="GitHub Issue number, for example 284 or P284")
    target.add_argument("--latest", action="store_true", help="Use the newest published article")
    parser.add_argument("--output", help="Optional path to write the generated Markdown pack")
    parser.add_argument("--stdout", action="store_true", help="Print the generated pack instead of writing a file")
    args = parser.parse_args()
    if args.output and args.stdout:
        parser.error("--output cannot be used with --stdout")
    return args


def main() -> int:
    args = parse_args()
    posts = load_posts()
    key, post = select_post(posts, args)
    markdown = find_backup(post).read_text(encoding="utf-8")
    pack = build_pack(post, markdown)

    if args.stdout:
        sys.stdout.write(pack)
    else:
        output_path = Path(args.output) if args.output else default_output_path(key, post)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pack, encoding="utf-8")
        print(f"Wrote {display_path(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

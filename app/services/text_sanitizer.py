import html
import re
from typing import Any


_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")
_GITHUB_STARS_RE = re.compile(r"\bGitHub\s+stars\b", re.IGNORECASE)
_MATCHED_TAGS_RE = re.compile(r"\bMatched\s+tags\s*:\s*[^.;，。；\n]*", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def clean_display_text(value: Any, *, max_length: int | None = None, default: str = "") -> str:
    """Turn README/LLM text into compact plain text for email and profiles."""
    if value is None:
        return default

    text = html.unescape(str(value))
    text = _MARKDOWN_HEADING_RE.sub("", text)
    text = _MARKDOWN_IMAGE_RE.sub(" ", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _GITHUB_STARS_RE.sub(" ", text)
    text = _MATCHED_TAGS_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" ;,，。；")

    if not text:
        return default
    if max_length is not None and len(text) > max_length:
        suffix = "..."
        if max_length <= len(suffix):
            return text[:max_length]
        return f"{text[: max_length - len(suffix)].rstrip()}{suffix}"
    return text


def clean_display_list(value: Any, *, max_items: int, item_max_length: int) -> list[str]:
    """Normalize list-like LLM output into bounded plain-text items."""
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str) and value.strip():
        raw_items = [value]
    else:
        raw_items = []

    items: list[str] = []
    for item in raw_items:
        cleaned = clean_display_text(item, max_length=item_max_length)
        if cleaned:
            items.append(cleaned)
        if len(items) >= max_items:
            break
    return items

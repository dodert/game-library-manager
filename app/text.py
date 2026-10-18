import html
import re

_BREAK = re.compile(r"<\s*(br\s*/?|/p|/div|/li|/h[1-6])\s*>", re.IGNORECASE)
_ITEM = re.compile(r"<\s*li[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def clean_html(value: str | None) -> str | None:
    """Plain text from text that may carry HTML (CLZ descriptions, provider synopses)."""
    if not value:
        return value
    if _TAG.search(value):
        # Like a browser: raw line breaks are just spaces, only tags break lines
        value = re.sub(r"\s*\n\s*", " ", value)
    if "<" in value or "&" in value:
        value = _BREAK.sub("\n", value)
        value = _ITEM.sub("• ", value)
        value = _TAG.sub("", value)
        value = html.unescape(value).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\r\n", "\n").split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None

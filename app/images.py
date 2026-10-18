import uuid
from pathlib import Path

import httpx

from .providers import MetadataProvider

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 3
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class ImageError(Exception):
    pass


async def fetch_image(http: httpx.AsyncClient, provider: MetadataProvider, url: str) -> tuple[bytes, str]:
    """Download an image from one of the provider's hosts. Returns (content, content_type)."""
    if not provider.allows_image_url(url):
        raise ImageError(f"URL not allowed for {provider.name}")
    target = provider.authorize_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        res = await http.get(target, follow_redirects=False)
        if res.is_redirect:
            target = str(res.next_request.url) if res.next_request else ""
            if not provider.allows_image_url(target):
                raise ImageError("Redirected to a host that is not allowed")
            continue
        break
    else:
        raise ImageError("Too many redirects")
    if res.status_code != 200:
        raise ImageError(f"HTTP {res.status_code}")
    content_type = res.headers.get("content-type", "").split(";")[0].strip()
    if content_type not in IMAGE_TYPES:
        raise ImageError(f"Not an image ({content_type or 'unknown type'})")
    if len(res.content) > MAX_IMAGE_BYTES:
        raise ImageError("Image too large")
    return res.content, content_type


async def save_first_cover(
    http: httpx.AsyncClient, provider: MetadataProvider, urls: list[str], covers_dir: Path, game_id: int
) -> str:
    """Try each URL in order and save the first one that works. Returns the stored filename."""
    errors = []
    for url in urls:
        try:
            content, content_type = await fetch_image(http, provider, url)
        except (ImageError, httpx.HTTPError) as exc:
            errors.append(str(exc) or exc.__class__.__name__)
            continue
        filename = f"{game_id}-{uuid.uuid4().hex[:8]}{IMAGE_TYPES[content_type]}"
        (covers_dir / filename).write_bytes(content)
        return filename
    raise ImageError("; ".join(errors) or "No cover URL")

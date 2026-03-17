from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Common tracking params that should not affect story identity.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url.strip())
    # Normalize host/scheme and remove tracking noise/fragments.
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))

    canonical = parsed._replace(
        scheme=scheme,
        netloc=netloc,
        path=path,
        params="",
        query=query,
        fragment="",
    )
    return urlunparse(canonical)


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t


def build_story_key(title: str | None, url: str | None) -> str:
    canonical_url = canonicalize_url(url) or ""
    normalized_title = normalize_title(title)
    material = f"{canonical_url}|{normalized_title}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

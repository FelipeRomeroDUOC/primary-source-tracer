"""Lightweight audiovisual helpers (YouTube transcripts/metadata & MCP image blocks)."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from primary_source_tracer.analyzer import PRIMARY_DOC_EXTENSIONS, categorize_domain

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_IMAGE_INLINE_BYTES = 450_000
MAX_IMAGE_DOWNLOAD_BYTES = 4_000_000

_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")


def extract_youtube_video_id(url: str) -> str | None:
    """Extract an 11-character YouTube video ID from standard watch/short/live/embed URLs."""
    parsed = urllib.parse.urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www.") or host.startswith("m."):
        host = host.split(".", 1)[1]

    if host == "youtu.be":
        vid = parsed.path.strip("/").split("/")[0]
        return vid if _YT_ID_RE.match(vid) else None

    if host in ("youtube.com", "youtube-nocookie.com"):
        parts = [p for p in parsed.path.split("/") if p]
        if parsed.path == "/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            vid = (qs.get("v") or [""])[0]
            return vid if _YT_ID_RE.match(vid) else None
        if len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v"):
            vid = parts[1]
            return vid if _YT_ID_RE.match(vid) else None
    return None


def format_timestamp_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def extract_urls_from_text(text: str) -> list[dict]:
    """Extract deduplicated outbound links from plain text (e.g., YouTube video descriptions)."""
    seen: set[str] = set()
    links: list[dict] = []
    for match in _URL_IN_TEXT_RE.finditer(text or ""):
        u = match.group(0).rstrip(".,;:")
        if not u or u in seen:
            continue
        seen.add(u)
        parsed = urllib.parse.urlparse(u)
        path_lower = (parsed.path or "").lower()
        dom_cat = categorize_domain(u)
        is_doc_ext = any(path_lower.endswith(ext) for ext in PRIMARY_DOC_EXTENSIONS)
        is_primary_candidate = (
            dom_cat != "social_or_video"
            and (is_doc_ext or dom_cat in ("institutional_gov", "academic_edu") or "doi.org" in (parsed.netloc or "").lower())
        )
        links.append({
            "url": u,
            "anchor_text": "[Enlace en descripción del video]",
            "domain_category": dom_cat,
            "is_primary_candidate": bool(is_primary_candidate),
        })
        if len(links) >= 12:
            break
    return links


def detect_image_mime(raw_bytes: bytes, content_type: str = "", url_or_path: str = "") -> str | None:
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"):
        return "image/jpeg" if ct == "image/jpg" else ct
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    if raw_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    lower = (url_or_path or "").lower().split("?")[0]
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return None


def prepare_image_mcp_block(
    raw_bytes: bytes,
    content_type: str = "",
    url_or_path: str = "",
) -> dict | None:
    """Convert raw image bytes into a compact MCP ImageContent dict, downscaling if needed."""
    mime = detect_image_mime(raw_bytes, content_type=content_type, url_or_path=url_or_path)
    if not mime or not raw_bytes:
        return None

    data_bytes = raw_bytes
    final_mime = mime
    if len(data_bytes) > MAX_IMAGE_INLINE_BYTES:
        try:
            try:
                import pymupdf as fitz  # type: ignore
            except ImportError:
                import fitz  # type: ignore

            doc = fitz.open(stream=raw_bytes, filetype=mime.split("/")[-1])
            page = doc[0]
            scale = min(1.0, 1100.0 / max(page.rect.width, page.rect.height, 1.0))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            data_bytes = pix.tobytes("jpeg", jpg_quality=78)
            final_mime = "image/jpeg"
            doc.close()
        except Exception:
            if len(data_bytes) > MAX_IMAGE_INLINE_BYTES:
                return None

    if len(data_bytes) > MAX_IMAGE_INLINE_BYTES:
        return None

    return {
        "data": base64.b64encode(data_bytes).decode("ascii"),
        "mimeType": final_mime,
    }


def _fetch_youtube_transcript(video_id: str) -> tuple[list[dict], str]:
    """Return (entries, transcript_type) where transcript_type is manual|auto_generated|unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        return [], "library_not_installed"

    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "list"):
            tlist = api.list(video_id)
            chosen = None
            t_type = "unavailable"
            try:
                chosen = tlist.find_manually_created_transcript(["es", "es-419", "es-ES", "en", "en-US", "en-GB"])
                t_type = "manual"
            except Exception:
                try:
                    chosen = tlist.find_generated_transcript(["es", "es-419", "es-ES", "en", "en-US", "en-GB"])
                    t_type = "auto_generated"
                except Exception:
                    for tr in tlist:
                        chosen = tr
                        t_type = "auto_generated" if getattr(tr, "is_generated", False) else "manual"
                        break
            if chosen is None:
                return [], "unavailable"
            fetched = chosen.fetch()
            entries = []
            for item in fetched:
                text = getattr(item, "text", None) if not isinstance(item, dict) else item.get("text")
                start = getattr(item, "start", 0.0) if not isinstance(item, dict) else item.get("start", 0.0)
                if text:
                    entries.append({"start": float(start), "text": " ".join(str(text).split())})
            return entries, t_type

        # Legacy v0.x fallback
        raw = YouTubeTranscriptApi.get_transcript(video_id, languages=["es", "en"])
        entries = [
            {"start": float(x.get("start", 0.0)), "text": " ".join(str(x.get("text", "")).split())}
            for x in raw
            if x.get("text")
        ]
        return entries, "auto_generated"
    except Exception:
        return [], "unavailable"


def fetch_youtube_source(url: str, timeout: int = 8, headers: dict | None = None) -> dict:
    """Fetch YouTube video metadata, description links, and timestamped transcript."""
    video_id = extract_youtube_video_id(url)
    if not video_id:
        return {
            "title": "",
            "text": "",
            "resource_type": "video",
            "outbound_links": [],
            "stock_images": [],
            "content_images": [],
            "has_table": False,
            "page_count": 1,
            "rendered_page_images": [],
            "inline_images": [],
            "media_metadata": {},
            "error": "URL de YouTube inválida.",
        }

    req_headers = dict(headers or {"User-Agent": "Mozilla/5.0"})
    title = ""
    channel = ""
    description = ""

    # 1. oEmbed metadata (fast, public, reliable)
    oembed_url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
    )
    try:
        req = urllib.request.Request(oembed_url, headers={"User-Agent": req_headers.get("User-Agent", "Mozilla/5.0")})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            meta = json.loads(resp.read(100_000).decode("utf-8", errors="ignore"))
        title = (meta.get("title") or "").strip()
        channel = (meta.get("author_name") or "").strip()
    except Exception:
        pass

    # 2. Extract description from watch page HTML for outbound bridge links
    try:
        watch_req = urllib.request.Request(f"https://www.youtube.com/watch?v={video_id}", headers=req_headers)
        with urllib.request.urlopen(watch_req, timeout=timeout) as resp:
            html = resp.read(600_000).decode("utf-8", errors="ignore")
        desc_match = re.search(r'"shortDescription":"((?:\\.|[^"\\])*)"', html)
        if desc_match:
            description = json.loads(f'"{desc_match.group(1)}"')
    except Exception:
        pass

    outbound_links = extract_urls_from_text(description)
    entries, transcript_type = _fetch_youtube_transcript(video_id)

    text_parts: list[str] = []
    if title or channel:
        text_parts.append(f"Video de YouTube: {title} | Canal: {channel}".strip())
    if description:
        text_parts.append("Descripción del video:\n" + description[:2000])

    if entries:
        lines = [f"[{format_timestamp_mmss(e['start'])}] {e['text']}" for e in entries[:450]]
        text_parts.append("Transcripción con marcas de tiempo:\n" + "\n".join(lines))
        error_msg = None
    else:
        error_msg = (
            "No se pudo obtener transcripción/subtítulos de este video de YouTube; "
            "solo se inspeccionaron metadatos y descripción."
        )

    return {
        "title": title or f"YouTube {video_id}",
        "text": "\n\n".join(text_parts),
        "resource_type": "video",
        "outbound_links": outbound_links,
        "stock_images": [],
        "content_images": [],
        "has_table": False,
        "page_count": 1,
        "rendered_page_images": [],
        "inline_images": [],
        "media_metadata": {
            "platform": "youtube",
            "video_id": video_id,
            "channel": channel,
            "canonical_url": f"https://youtu.be/{video_id}",
            "transcript_type": transcript_type,
            "transcript_segments": len(entries),
        },
        "error": error_msg,
    }

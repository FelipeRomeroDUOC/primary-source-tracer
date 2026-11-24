"""Deterministic, XSS-safe HTML evidence dossier generator with audiovisual embeds."""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any

from primary_source_tracer.audiovisual import (
    IMAGE_EXTENSIONS,
    extract_youtube_video_id,
    format_timestamp_mmss,
)


def _esc(val: Any) -> str:
    return html.escape(str(val or "").strip(), quote=True)


def _safe_http_url(url: str) -> str:
    clean = (url or "").strip()
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return clean


def _extract_start_seconds(url: str, explicit_seconds: Any = None) -> int:
    if explicit_seconds is not None:
        try:
            return max(0, int(explicit_seconds))
        except (TypeError, ValueError):
            pass
    parsed = urllib.parse.urlparse(url or "")
    qs = urllib.parse.parse_qs(parsed.query)
    raw_t = (qs.get("t") or qs.get("start") or [""])[0].strip().lower()
    if not raw_t:
        return 0
    if raw_t.isdigit():
        return int(raw_t)
    m = re.match(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$", raw_t)
    if m and any(m.groups()):
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return 0


def _is_image_item(url: str, media_type: str = "") -> bool:
    if (media_type or "").lower() == "image":
        return True
    lower = (url or "").lower().split("?")[0]
    return lower.endswith(IMAGE_EXTENSIONS)


def _render_media_block(item: dict) -> str:
    url = _safe_http_url(item.get("url", ""))
    if not url:
        return ""
    media_type = (item.get("media_type") or "").lower()
    vid = extract_youtube_video_id(url)
    if vid or media_type == "youtube":
        if not vid:
            return ""
        start_sec = _extract_start_seconds(url, item.get("start_seconds"))
        embed_url = f"https://www.youtube-nocookie.com/embed/{vid}" + (f"?start={start_sec}" if start_sec > 0 else "")
        watch_url = f"https://youtu.be/{vid}" + (f"?t={start_sec}" if start_sec > 0 else "")
        ts_label = f" ({format_timestamp_mmss(start_sec)})" if start_sec > 0 else ""
        return (
            '<div class="media-box">'
            '<div class="video-wrap">'
            f'<iframe src="{_esc(embed_url)}" title="{_esc(item.get("title") or "YouTube video")}" '
            'loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
            'allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>'
            "</div>"
            f'<div class="media-fallback">Si el visor bloquea iframes externos, abre el video directo: '
            f'<a href="{_esc(watch_url)}" target="_blank" rel="noopener noreferrer">Abrir en YouTube{_esc(ts_label)} ↗</a></div>'
            "</div>"
        )

    if _is_image_item(url, media_type):
        caption = _esc(item.get("caption") or item.get("title") or "Evidencia visual")
        return (
            '<figure class="media-box image-figure">'
            f'<img src="{_esc(url)}" alt="{caption}" loading="lazy" />'
            f'<figcaption>{caption} · '
            f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">Abrir imagen original ↗</a></figcaption>'
            "</figure>"
        )
    return ""


def _render_primary_card(item: dict) -> str:
    title = _esc(item.get("title") or item.get("url") or "Fuente sin título")
    url = _safe_http_url(item.get("url", ""))
    role = _esc(item.get("role") or "Evidencia primaria")
    access = _esc(item.get("access_status") or "")
    summary = _esc((item.get("summary") or "")[:800])
    excerpt = _esc((item.get("excerpt") or "")[:500])

    badge_html = f'<span class="badge badge-primary">{role}</span>'
    if access:
        badge_html += f' <span class="badge badge-access">{access}</span>'

    link_html = (
        f'<a class="source-link" href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{_esc(url)} ↗</a>'
        if url
        else '<span class="muted">Sin URL verificable</span>'
    )
    excerpt_html = f'<blockquote class="excerpt">“{excerpt}”</blockquote>' if excerpt else ""
    media_html = _render_media_block(item)

    return (
        '<article class="card">'
        f'<div class="badges">{badge_html}</div>'
        f"<h3>{title}</h3>"
        f'<div class="link-row">{link_html}</div>'
        + (f"<p>{summary}</p>" if summary else "")
        + excerpt_html
        + media_html
        + "</article>"
    )


def _render_secondary_row(item: dict) -> str:
    title = _esc(item.get("title") or item.get("url") or "Fuente secundaria")
    url = _safe_http_url(item.get("url", ""))
    classification = _esc(item.get("classification") or "Secundaria")
    reason = _esc((item.get("reason") or "")[:400])
    title_cell = (
        f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{title} ↗</a>'
        if url
        else title
    )
    return (
        "<tr>"
        f"<td>{title_cell}</td>"
        f'<td><span class="badge badge-secondary">{classification}</span></td>'
        f"<td>{reason}</td>"
        "</tr>"
    )


def build_evidence_dossier_html(
    topic: str,
    verdict: str,
    primary_sources: list[dict] | None = None,
    secondary_sources: list[dict] | None = None,
    notes: list[str] | None = None,
) -> str:
    """Build a clean, self-contained HTML evidence dossier with audiovisual embeds."""
    primaries = [p for p in (primary_sources or []) if isinstance(p, dict)][:12]
    secondaries = [s for s in (secondary_sources or []) if isinstance(s, dict)][:16]
    clean_notes = [str(n).strip()[:300] for n in (notes or []) if str(n).strip()][:8]

    primary_cards = "\n".join(_render_primary_card(p) for p in primaries) or (
        '<p class="muted">No se verificaron fuentes primarias a texto completo en esta sesión.</p>'
    )
    secondary_rows = "\n".join(_render_secondary_row(s) for s in secondaries)
    secondary_section = (
        '<details class="secondary-block" open>'
        f"<summary>Fuentes Secundarias Evaluadas ({len(secondaries)})</summary>"
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Fuente</th><th>Clasificación</th><th>Razón</th>"
        "</tr></thead><tbody>"
        + (secondary_rows or '<tr><td colspan="3" class="muted">Ninguna fuente secundaria registrada.</td></tr>')
        + "</tbody></table></div></details>"
    )
    notes_html = (
        '<section class="notes-block"><h2>Limitaciones y Fricciones</h2><ul>'
        + "".join(f"<li>{_esc(n)}</li>" for n in clean_notes)
        + "</ul></section>"
        if clean_notes
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dossier de Evidencia — {_esc(topic)}</title>
  <style>
    :root {{
      --bg: #0b1120;
      --card: #131c31;
      --border: rgba(148, 163, 184, 0.22);
      --text: #f8fafc;
      --muted: #94a3b8;
      --emerald: #10b981;
      --sky: #38bdf8;
      --amber: #f59e0b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px 18px 56px;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
      line-height: 1.55;
    }}
    .wrap {{ max-width: 920px; margin: 0 auto; }}
    header {{
      padding: 24px 26px;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(16,185,129,0.14), rgba(56,189,248,0.08));
      border: 1px solid rgba(16,185,129,0.35);
      margin-bottom: 24px;
    }}
    .kicker {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--emerald);
      margin-bottom: 8px;
    }}
    h1 {{ margin: 0 0 12px; font-size: 26px; line-height: 1.2; }}
    h2 {{ font-size: 18px; margin: 28px 0 14px; color: var(--sky); }}
    h3 {{ margin: 10px 0 6px; font-size: 17px; }}
    .verdict {{ margin: 0; color: var(--text); font-size: 15px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px 20px;
      margin-bottom: 16px;
    }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }}
    .badge-primary {{ background: rgba(16,185,129,0.16); color: var(--emerald); border: 1px solid rgba(16,185,129,0.45); }}
    .badge-access {{ background: rgba(56,189,248,0.14); color: var(--sky); border: 1px solid rgba(56,185,248,0.35); }}
    .badge-secondary {{ background: rgba(245,158,11,0.14); color: var(--amber); border: 1px solid rgba(245,158,11,0.35); }}
    .link-row {{ margin: 6px 0 10px; font-size: 13px; word-break: break-all; }}
    a {{ color: var(--sky); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .excerpt {{
      margin: 10px 0;
      padding: 10px 14px;
      border-left: 3px solid var(--emerald);
      background: rgba(15, 23, 42, 0.7);
      color: #cbd5e1;
      font-size: 14px;
      border-radius: 0 8px 8px 0;
    }}
    .media-box {{ margin-top: 14px; }}
    .video-wrap {{
      position: relative;
      padding-bottom: 56.25%;
      height: 0;
      overflow: hidden;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #020617;
    }}
    .video-wrap iframe {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      border: 0;
    }}
    .media-fallback {{
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .image-figure {{ margin: 14px 0 0; }}
    .image-figure img {{
      max-width: 100%;
      max-height: 460px;
      border-radius: 12px;
      border: 1px solid var(--border);
      display: block;
    }}
    .image-figure figcaption {{
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .secondary-block {{
      margin-top: 24px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px 18px;
    }}
    .secondary-block summary {{
      cursor: pointer;
      font-weight: 700;
      font-size: 16px;
      color: var(--amber);
    }}
    .table-wrap {{ overflow-x: auto; margin-top: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
    th, td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 700; }}
    .notes-block {{
      margin-top: 22px;
      padding: 16px 20px;
      border-radius: 16px;
      background: var(--card);
      border: 1px solid var(--border);
      font-size: 14px;
    }}
    .muted {{ color: var(--muted); }}
    footer {{
      margin-top: 28px;
      text-align: center;
      font-size: 12px;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="kicker">Primary Source Tracer · Dossier de Evidencia</div>
      <h1>{_esc(topic)}</h1>
      <p class="verdict">{_esc(verdict)}</p>
    </header>
    <section>
      <h2>Evidencia Primaria, Contraste y Pruebas Audiovisuales</h2>
      {primary_cards}
    </section>
    {secondary_section}
    {notes_html}
    <footer>Generado con Primary Source Tracer · Verifica siempre cada enlace original.</footer>
  </div>
</body>
</html>
"""

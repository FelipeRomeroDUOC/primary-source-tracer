"""Local domain-agnostic MCP server for Primary Source Tracer."""

from __future__ import annotations

import contextlib
import hashlib
import http.cookiejar
import io
import json
import logging
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from primary_source_tracer.analyzer import (
    analyze_document_text,
    categorize_domain,
    compute_echo_clusters,
    extract_html_content,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
    "Upgrade-Insecure-Requests": "1",
}
MAX_PAYLOAD_BYTES = 11500


def _render_scanned_pdf_pages(raw_bytes: bytes, max_pages: int = 3) -> tuple[str, int, list[str]]:
    rendered_paths: list[str] = []
    try:
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            import fitz  # type: ignore

        try:
            fitz.TOOLS.mupdf_display_errors(False)
            fitz.TOOLS.mupdf_display_warnings(False)
        except Exception:
            pass

        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        count = len(doc)
        pages = [doc[i].get_text("text") or "" for i in range(min(count, 40))]
        joined = "\n".join(pages).strip()
        if len(joined) < 20 and count > 0:
            img_count = sum(len(doc[i].get_images()) for i in range(min(count, 10)))
            if img_count > 0:
                out_dir = Path(tempfile.gettempdir()) / "primary_source_tracer_pages"
                out_dir.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha1(raw_bytes[:65536]).hexdigest()[:10]
                for i in range(min(count, max_pages)):
                    png_path = out_dir / f"scan_{digest}_p{i + 1}.png"
                    if not png_path.exists():
                        pix = doc[i].get_pixmap(dpi=150)
                        pix.save(str(png_path))
                    rendered_paths.append(str(png_path))
                joined = (
                    f"[SCANNED_FACSIMILE_PDF: {count} página(s) con {img_count} imagen(es) escaneada(s) "
                    f"sin capa OCR; {len(rendered_paths)} página(s) renderizadas a PNG en rendered_page_images]"
                )
        doc.close()
        return joined, count, rendered_paths
    except Exception:
        return "", 1, []


def _extract_pdf_bytes(raw_bytes: bytes) -> tuple[str, int, list[str]]:
    pypdf_text = ""
    pypdf_count = 0
    try:
        import pypdf  # type: ignore

        logging.getLogger("pypdf").setLevel(logging.ERROR)
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages[:40]]
        pypdf_text = "\n".join(pages).strip()
        pypdf_count = len(reader.pages)
        if len(pypdf_text) >= 20:
            return pypdf_text, pypdf_count, []
    except Exception:
        pass

    fitz_text, fitz_count, rendered_paths = _render_scanned_pdf_pages(raw_bytes)
    if len(fitz_text) >= 20 or rendered_paths:
        return fitz_text, max(fitz_count, pypdf_count, 1), rendered_paths

    decoded = raw_bytes.decode("latin-1", errors="ignore")
    chunks = re.findall(r"\(([^\(\)\\]{4,200})\)", decoded)
    text = " ".join(c for c in chunks if re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ0-9]{3,}", c))
    page_matches = re.findall(r"/Type\s*/Page\b", decoded)
    return text or pypdf_text, max(len(page_matches), pypdf_count, fitz_count, 1), []


def parse_openalex_work(payload: dict) -> dict:
    title = payload.get("title") or payload.get("display_name") or ""
    year = payload.get("publication_year")
    cited_by = payload.get("cited_by_count", 0)
    oa_info = payload.get("open_access") or {}
    best_oa = payload.get("best_oa_location") or {}
    oa_pdf_url = best_oa.get("pdf_url") or oa_info.get("oa_url") or ""

    authors: list[str] = []
    for auth in (payload.get("authorships") or [])[:8]:
        name = (auth.get("author") or {}).get("display_name")
        if name:
            authors.append(name)

    inv = payload.get("abstract_inverted_index") or {}
    abstract_text = ""
    if isinstance(inv, dict) and inv:
        pos_to_word: dict[int, str] = {}
        for word, positions in inv.items():
            for pos in positions or []:
                if isinstance(pos, int):
                    pos_to_word[pos] = word
        if pos_to_word:
            max_pos = min(max(pos_to_word.keys()), 400)
            abstract_text = " ".join(pos_to_word[i] for i in range(max_pos + 1) if i in pos_to_word)

    return {
        "canonical_title": title,
        "publication_year": year,
        "authors": authors,
        "cited_by_count": cited_by,
        "is_open_access": bool(oa_info.get("is_oa") or oa_pdf_url),
        "oa_pdf_url": oa_pdf_url,
        "abstract_text": abstract_text[:1000],
    }


def resolve_open_access_via_api(doi: str, timeout: int = 6) -> dict | None:
    clean_doi = (doi or "").strip()
    if not clean_doi:
        return None
    api_url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(clean_doi, safe='/')}"
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read(500_000).decode("utf-8", errors="ignore"))
        parsed = parse_openalex_work(payload)
        parsed["doi"] = clean_doi
        parsed["source_api"] = "openalex"
        return parsed
    except Exception:
        return None


def _infer_resource_type(url_or_path: str, content_type: str = "") -> str:
    lower = url_or_path.lower().split("?")[0]
    ct = content_type.lower()
    if lower.endswith(".pdf") or "application/pdf" in ct:
        return "pdf"
    if lower.endswith((".csv", ".xlsx", ".xls", ".json", ".xml")) or any(
        k in ct for k in ("csv", "spreadsheet", "excel")
    ):
        return "dataset"
    if lower.endswith((".doc", ".docx", ".rtf", ".odt")):
        return "doc"
    return "html"


def fetch_document(url_or_path: str, timeout: int = 8) -> dict:
    target = (url_or_path or "").strip()
    local_candidate: Path | None = None
    if target.startswith("file:///"):
        parsed_path = urllib.parse.unquote(urllib.parse.urlparse(target).path)
        if re.match(r"^/[A-Za-z]:/", parsed_path):
            parsed_path = parsed_path[1:]
        local_candidate = Path(parsed_path)
    elif not target.startswith(("http://", "https://")):
        p = Path(target)
        if p.exists():
            local_candidate = p

    if local_candidate is not None and local_candidate.exists():
        raw_bytes = local_candidate.read_bytes()
        res_type = _infer_resource_type(str(local_candidate))
        if res_type == "pdf" or raw_bytes.lstrip()[:4] == b"%PDF":
            text, page_count, rendered_images = _extract_pdf_bytes(raw_bytes)
            return {
                "title": local_candidate.name,
                "text": text,
                "resource_type": "pdf",
                "outbound_links": [],
                "stock_images": [],
                "has_table": "|" in text or "\t" in text,
                "page_count": page_count,
                "rendered_page_images": rendered_images,
                "error": None,
            }
        html_str = raw_bytes.decode("utf-8", errors="ignore")
        parsed = extract_html_content(html_str, local_candidate.as_uri())
        return {
            "title": parsed["title"] or local_candidate.name,
            "text": parsed["text"],
            "resource_type": res_type,
            "outbound_links": parsed["outbound_links"],
            "stock_images": parsed["stock_images"],
            "has_table": parsed["has_table"],
            "page_count": 1,
            "rendered_page_images": [],
            "error": None,
        }

    if not target.startswith(("http://", "https://")):
        return {
            "title": "",
            "text": "",
            "resource_type": _infer_resource_type(target),
            "outbound_links": [],
            "stock_images": [],
            "has_table": False,
            "page_count": 1,
            "rendered_page_images": [],
            "error": "Archivo o URL no encontrado.",
        }

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(target, headers=BROWSER_HEADERS)
    try:
        with opener.open(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw_bytes = resp.read(2_500_000)
            is_pdf_bytes = raw_bytes.lstrip()[:4] == b"%PDF" or "application/pdf" in content_type.lower()
            if is_pdf_bytes:
                text, page_count, rendered_images = _extract_pdf_bytes(raw_bytes)
                return {
                    "title": Path(urllib.parse.urlparse(target).path).name or target,
                    "text": text,
                    "resource_type": "pdf",
                    "outbound_links": [],
                    "stock_images": [],
                    "has_table": "|" in text or "\t" in text,
                    "page_count": page_count,
                    "rendered_page_images": rendered_images,
                    "error": None,
                }
            res_type = "html" if "text/html" in content_type.lower() else _infer_resource_type(target, content_type)
            html_str = raw_bytes.decode("utf-8", errors="ignore")
            parsed = extract_html_content(html_str, target)
            return {
                "title": parsed["title"],
                "text": parsed["text"],
                "resource_type": res_type,
                "outbound_links": parsed["outbound_links"],
                "stock_images": parsed["stock_images"],
                "has_table": parsed["has_table"],
                "page_count": 1,
                "rendered_page_images": [],
                "error": None,
            }
    except Exception as exc:
        return {
            "title": "",
            "text": "",
            "resource_type": _infer_resource_type(target),
            "outbound_links": [],
            "stock_images": [],
            "has_table": False,
            "page_count": 1,
            "rendered_page_images": [],
            "error": f"Error al descargar fuente: {type(exc).__name__}: {exc}",
        }


class _DDGResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in_title_a = False
        self._in_snippet = False
        self._curr: dict = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        cls = attr_map.get("class", "")
        if tag.lower() == "a" and "result__a" in cls:
            href = attr_map.get("href", "")
            if "uddg=" in href:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = qs.get("uddg", [href])[0]
            self._curr = {"url": href, "title": "", "snippet": ""}
            self._in_title_a = True
        elif "result__snippet" in cls and self._curr:
            self._in_snippet = True

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._in_title_a:
            self._in_title_a = False
        elif self._in_snippet and tag.lower() in ("a", "div", "span", "td"):
            self._in_snippet = False
            if self._curr.get("url"):
                self.results.append(self._curr)
                self._curr = {}

    def handle_data(self, data: str):
        if self._in_title_a:
            self._curr["title"] += data
        elif self._in_snippet:
            self._curr["snippet"] += data


def _enforce_budget(payload: dict) -> dict:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(raw) <= MAX_PAYLOAD_BYTES:
        return payload
    if "matched_excerpts" in payload:
        payload["matched_excerpts"] = payload["matched_excerpts"][:2]
    if "outbound_links" in payload:
        payload["outbound_links"] = payload["outbound_links"][:6]
    if "evaluated_sources" in payload:
        for src in payload["evaluated_sources"]:
            src["matched_excerpts"] = src.get("matched_excerpts", [])[:2]
            src["outbound_links"] = src.get("outbound_links", [])[:4]
    return payload


def tool_search_web_candidates(queries: list[str], max_results_per_query: int = 8) -> dict:
    candidates: list[dict] = []
    seen_urls: set[str] = set()
    cap = max(1, min(int(max_results_per_query or 8), 12))

    for q in (queries or [])[:6]:
        query_str = (q or "").strip()
        if not query_str:
            continue
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query_str})
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                html_str = resp.read(500_000).decode("utf-8", errors="ignore")
            parser = _DDGResultParser()
            parser.feed(html_str)
            count = 0
            for item in parser.results:
                u = item["url"].strip()
                if not u or u in seen_urls or not u.startswith(("http://", "https://")):
                    continue
                seen_urls.add(u)
                parsed = urllib.parse.urlparse(u)
                candidates.append({
                    "query_used": query_str,
                    "title": " ".join(item["title"].split())[:160],
                    "url": u,
                    "domain": (parsed.netloc or "").lower(),
                    "resource_type": _infer_resource_type(u),
                    "domain_category": categorize_domain(u),
                    "snippet": " ".join(item["snippet"].split())[:240],
                })
                count += 1
                if count >= cap:
                    break
        except Exception as exc:
            candidates.append({
                "query_used": query_str,
                "title": "[Error en consulta de búsqueda]",
                "url": "",
                "domain": "",
                "resource_type": "html",
                "domain_category": "other",
                "snippet": f"{type(exc).__name__}: {exc}",
            })

    return _enforce_budget({
        "note": "domain_category y resource_type son descriptivos; NO implican que una fuente sea primaria. Inspeccione cada candidato con inspect_and_classify_source.",
        "total_candidates": len(candidates),
        "candidates": candidates,
    })


def _attach_browserless_enhancements(analysis: dict, fetched: dict) -> dict:
    analysis["title"] = fetched.get("title", "")
    analysis["rendered_page_images"] = fetched.get("rendered_page_images", [])
    if analysis["rendered_page_images"]:
        analysis["primary_signals"].append(
            f"PDF escaneado renderizado sin navegador a {len(analysis['rendered_page_images'])} imagen(es) PNG local(es)."
        )
    if fetched.get("error"):
        analysis["friction_signals"].append(fetched["error"])
        if analysis["preliminary_classification"] == "unreachable_or_empty":
            analysis["classification_reasons"].append(fetched["error"])

    if analysis.get("preliminary_classification") == "paywalled_abstract_only":
        dois = analysis.get("detected_identifiers") or []
        if dois:
            oa_data = resolve_open_access_via_api(dois[0])
            if oa_data:
                analysis["open_access_resolution"] = oa_data
                oa_url = oa_data.get("oa_pdf_url")
                if oa_url:
                    analysis["outbound_links"].insert(
                        0,
                        {
                            "url": oa_url,
                            "anchor_text": f"[OpenAlex Open Access PDF] {oa_data.get('canonical_title', '')}",
                            "domain_category": categorize_domain(oa_url),
                            "is_primary_candidate": True,
                        },
                    )
    return analysis


def tool_inspect_and_classify_source(
    url_or_path: str,
    agent_evidence_markers: list[str] | None = None,
    max_excerpts: int = 5,
) -> dict:
    fetched = fetch_document(url_or_path)
    analysis = analyze_document_text(
        text=fetched["text"],
        url_or_path=url_or_path,
        resource_type=fetched["resource_type"],
        agent_evidence_markers=agent_evidence_markers or [],
        outbound_links=fetched["outbound_links"],
        stock_images=fetched["stock_images"],
        has_table=fetched["has_table"],
        page_count=fetched["page_count"],
        max_excerpts=max(1, min(int(max_excerpts or 5), 6)),
    )
    analysis = _attach_browserless_enhancements(analysis, fetched)
    return _enforce_budget(analysis)


def tool_compare_echo_and_trace(
    urls: list[str],
    agent_evidence_markers: list[str] | None = None,
    follow_bridge_links: bool = True,
    max_bridge_hops: int = 4,
) -> dict:
    markers = agent_evidence_markers or []
    evaluated: list[dict] = []
    raw_texts_for_echo: list[dict] = []
    visited_keys: set[str] = set()
    bridge_paths: list[dict] = []

    def _norm_key(u: str) -> str:
        if u.startswith("file:///"):
            parsed_path = urllib.parse.unquote(urllib.parse.urlparse(u).path)
            if re.match(r"^/[A-Za-z]:/", parsed_path):
                parsed_path = parsed_path[1:]
            return str(Path(parsed_path).resolve()).lower()
        p = Path(u)
        if not u.startswith(("http://", "https://")) and p.exists():
            return str(p.resolve()).lower()
        return u.strip()

    for u in (urls or [])[:10]:
        key = _norm_key(u)
        if not key or key in visited_keys:
            continue
        visited_keys.add(key)
        fetched = fetch_document(u)
        raw_texts_for_echo.append({"url": u, "text": fetched["text"]})
        analysis = analyze_document_text(
            text=fetched["text"],
            url_or_path=u,
            resource_type=fetched["resource_type"],
            agent_evidence_markers=markers,
            outbound_links=fetched["outbound_links"],
            stock_images=fetched["stock_images"],
            has_table=fetched["has_table"],
            page_count=fetched["page_count"],
            max_excerpts=3,
        )
        analysis = _attach_browserless_enhancements(analysis, fetched)
        analysis["hop_depth"] = 0
        evaluated.append(analysis)

    if follow_bridge_links:
        hops_done = 0
        cap_hops = max(0, min(int(max_bridge_hops or 4), 6))
        initial_sources = list(evaluated)
        for src in initial_sources:
            if hops_done >= cap_hops:
                break
            for link in src.get("outbound_links", []):
                if hops_done >= cap_hops:
                    break
                if not link.get("is_primary_candidate"):
                    continue
                target_url = link["url"]
                key = _norm_key(target_url)
                if key in visited_keys:
                    continue
                visited_keys.add(key)
                hops_done += 1
                fetched = fetch_document(target_url)
                raw_texts_for_echo.append({"url": target_url, "text": fetched["text"]})
                hop_analysis = analyze_document_text(
                    text=fetched["text"],
                    url_or_path=target_url,
                    resource_type=fetched["resource_type"],
                    agent_evidence_markers=markers,
                    outbound_links=fetched["outbound_links"],
                    stock_images=fetched["stock_images"],
                    has_table=fetched["has_table"],
                    page_count=fetched["page_count"],
                    max_excerpts=3,
                )
                hop_analysis = _attach_browserless_enhancements(hop_analysis, fetched)
                hop_analysis["hop_depth"] = 1
                hop_analysis["reached_from"] = src["url_or_path"]
                evaluated.append(hop_analysis)
                bridge_paths.append({
                    "from_secondary_url": src["url_or_path"],
                    "to_candidate_url": target_url,
                    "anchor_text": link.get("anchor_text", ""),
                    "target_classification": hop_analysis["preliminary_classification"],
                })

    echo_clusters = compute_echo_clusters(raw_texts_for_echo)
    echo_url_to_reason = {
        u: c["reason"] for c in echo_clusters for u in c.get("urls", [])
    }
    for src in evaluated:
        if src["url_or_path"] in echo_url_to_reason:
            src["classification_reasons"].append(echo_url_to_reason[src["url_or_path"]])

    summary_counts = {
        "total_evaluated": len(evaluated),
        "likely_primary": sum(1 for s in evaluated if s["preliminary_classification"] == "likely_primary"),
        "paywalled_abstract_only": sum(
            1 for s in evaluated if s["preliminary_classification"] == "paywalled_abstract_only"
        ),
        "official_or_pdf_but_secondary": sum(
            1 for s in evaluated if s["preliminary_classification"] == "official_or_pdf_but_secondary"
        ),
        "secondary_bridge": sum(1 for s in evaluated if s["preliminary_classification"] == "secondary_bridge"),
        "secondary_no_outbound_proof": sum(
            1 for s in evaluated if s["preliminary_classification"] == "secondary_no_outbound_proof"
        ),
        "unreachable_or_empty": sum(
            1 for s in evaluated if s["preliminary_classification"] == "unreachable_or_empty"
        ),
    }

    return _enforce_budget({
        "summary_counts": summary_counts,
        "echo_clusters": echo_clusters,
        "bridge_paths": bridge_paths,
        "evaluated_sources": evaluated,
    })


MCP_TOOLS = [
    {
        "name": "search_web_candidates",
        "description": (
            "Ejecuta consultas web dinámicas definidas por el agente para descubrir fuentes candidatas. "
            "100% agnóstico al tema: el agente debe construir las consultas para el dominio solicitado."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Consultas de búsqueda diseñadas por el agente para el tema del usuario.",
                },
                "max_results_per_query": {
                    "type": "integer",
                    "default": 8,
                    "description": "Máximo de resultados por consulta (1-12).",
                },
            },
            "required": ["queries"],
        },
    },
    {
        "name": "inspect_and_classify_source",
        "description": (
            "Inspecciona una URL (HTML o PDF) o archivo PDF/HTML local sin necesidad de navegador. "
            "Evalúa señales estructurales (primaria vs. secundaria/falso primario PDF/.gov/paywall), "
            "renderiza automáticamente páginas de PDFs escaneados a PNG y resuelve DOIs vía OpenAlex."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url_or_path": {
                    "type": "string",
                    "description": "URL remota o ruta local al archivo HTML/PDF.",
                },
                "agent_evidence_markers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Marcadores, unidades, identificadores o términos probatorios definidos dinámicamente por el agente para el tema actual.",
                },
                "max_excerpts": {
                    "type": "integer",
                    "default": 5,
                    "description": "Número máximo de extractos a devolver.",
                },
            },
            "required": ["url_or_path"],
        },
    },
    {
        "name": "compare_echo_and_trace",
        "description": (
            "Inspecciona en lote múltiples fuentes sin navegador, detecta clústeres de eco (artículos clonados por similitud TF-IDF), "
            "sigue enlaces salientes desde fuentes puente o copias abiertas OpenAlex hacia candidatos a documento primario (1 salto) y conserva "
            "todas las fuentes secundarias con la razón explícita de su clasificación."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de URLs o rutas locales a evaluar (máx. 10).",
                },
                "agent_evidence_markers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Marcadores probatorios definidos por el agente para el tema actual.",
                },
                "follow_bridge_links": {
                    "type": "boolean",
                    "default": True,
                    "description": "Si es True, sigue automáticamente enlaces hacia documentos candidatos encontrados en fuentes puente.",
                },
                "max_bridge_hops": {
                    "type": "integer",
                    "default": 4,
                    "description": "Máximo de enlaces puente a seguir automáticamente.",
                },
            },
            "required": ["urls"],
        },
    },
]


def handle_jsonrpc_request(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "primary-source-tracer", "version": "0.1.0"},
            },
        }
    if method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            with contextlib.redirect_stdout(sys.stderr):
                if name == "search_web_candidates":
                    data = tool_search_web_candidates(
                        queries=args.get("queries") or [],
                        max_results_per_query=args.get("max_results_per_query", 8),
                    )
                elif name == "inspect_and_classify_source":
                    data = tool_inspect_and_classify_source(
                        url_or_path=args.get("url_or_path", ""),
                        agent_evidence_markers=args.get("agent_evidence_markers") or [],
                        max_excerpts=args.get("max_excerpts", 5),
                    )
                elif name == "compare_echo_and_trace":
                    data = tool_compare_echo_and_trace(
                        urls=args.get("urls") or [],
                        agent_evidence_markers=args.get("agent_evidence_markers") or [],
                        follow_bridge_links=args.get("follow_bridge_links", True),
                        max_bridge_hops=args.get("max_bridge_hops", 4),
                    )
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Unknown tool: {name}"},
                    }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool execution error: {type(exc).__name__}: {exc}"}],
                    "isError": True,
                },
            }
    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            continue
        resp = handle_jsonrpc_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=True) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

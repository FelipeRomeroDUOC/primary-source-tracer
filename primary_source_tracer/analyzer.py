"""Domain-agnostic structural analyzer for Primary Source Tracer."""

from __future__ import annotations

import math
import re
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

STOCK_DOMAINS = (
    "istockphoto.com",
    "shutterstock.com",
    "gettyimages.",
    "unsplash.com",
    "freepik.com",
    "stock.adobe.com",
    "depositphotos.com",
    "pexels.com",
    "pixabay.com",
)

SOCIAL_DOMAINS = (
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "pinterest.",
    "linkedin.com",
)

ATTRIBUTION_PATTERNS = (
    r"\bsegún\b",
    r"\bde acuerdo con\b",
    r"\bcitado por\b",
    r"\bfuente:\s*",
    r"\binformaron\b",
    r"\breportes de prensa\b",
    r"\baccording to\b",
    r"\bas reported by\b",
    r"\bcited in\b",
    r"\bsource:\s*",
    r"\bstudy by\b",
)

SECONDARY_FORMAT_PATTERNS = (
    r"\bcomunicado de prensa\b",
    r"\bnota de prensa\b",
    r"\bboletín\b",
    r"\bpress release\b",
    r"\bfact sheet\b",
    r"\bpolicy brief\b",
    r"\bbackground\s*guide\b",
    r"\bstudy\s*guide\b",
    r"\bmodel united nations\b",
    r"\bquestions to consider\b",
    r"\bliterature review\b",
    r"\bsystematic review\b",
    r"\brevisión sistemática\b",
    r"\bmeta-analysis\b",
    r"\bmeta-análisis\b",
    r"\boverview\b",
    r"\bresumen ejecutivo\b",
)

ENCYCLOPEDIA_HOSTS = (
    "wikipedia.org",
    "britannica.com",
    "scholarpedia.org",
)

PAYWALL_PATTERNS = (
    r"\baccess via your institution\b",
    r"\binstitutional login\b",
    r"\bbuy article\b",
    r"\bpurchase pdf\b",
    r"\bsubscribe to\b",
    r"\babout this article\b",
    r"\bcite this article\b",
    r"\bdownload citation\b",
    r"\bget access\b",
    r"\brent or buy\b",
)

BOT_CHALLENGE_PATTERNS = (
    r"\bclient challenge\b",
    r"\benable javascript and cookies to continue\b",
    r"\bplease enable javascript\b",
    r"\bchecking your browser\b",
    r"\bverify you are human\b",
    r"\bray id:\s*[0-9a-f]+\b",
    r"\bpardon our interruption\b",
)

DOI_REGEX = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b")

PRIMARY_DOC_EXTENSIONS = (".pdf", ".csv", ".xlsx", ".xls", ".json", ".xml", ".zip")

BIBLIOGRAPHIC_STUB_HOSTS = (
    "pubmed.ncbi.nlm.nih.gov",
    "eric.ed.gov",
    "semanticscholar.org",
    "openalex.org",
)

NOISY_QUERY_KEYS = {"term", "q", "query", "search", "s", "author", "authors"}
NOISY_PATH_SEGMENTS = ("/search", "/help", "/login", "/signin", "/signup", "/register", "/cart", "/subscribe")


def _is_noisy_search_or_nav_url(url: str) -> bool:
    parsed = urlparse(url)
    path_lower = (parsed.path or "").lower()
    if any(seg in path_lower for seg in NOISY_PATH_SEGMENTS):
        return True
    qs = parse_qs(parsed.query or "")
    if any(k.lower() in NOISY_QUERY_KEYS for k in qs):
        return True
    return False


def categorize_domain(url_or_path: str) -> str:
    parsed = urlparse(url_or_path)
    host = (parsed.netloc or "").lower()
    if not host:
        return "other"
    if any(s in host for s in SOCIAL_DOMAINS):
        return "social_or_video"
    if (
        host.endswith(".gov")
        or host.endswith(".gob")
        or ".gov." in host
        or ".gob." in host
        or host.endswith(".mil")
        or "granicus.com" in host
        or "tribunal" in host
    ):
        return "institutional_gov"
    if (
        host.endswith(".edu")
        or ".edu." in host
        or host.endswith(".ac.uk")
        or "arxiv.org" in host
        or "scielo." in host
        or "rae.es" in host
        or "archive.org" in host
    ):
        return "academic_edu"
    if any(k in host for k in ("news", "diario", "radio", "blog", "wordpress", "medium.com", "theguardian", "bbc.", "20minutos", "eldebate", "elespanol")):
        return "media_or_blog"
    return "other"


class _CleanHTMLParser(HTMLParser):
    IGNORED_TAGS = {"script", "style", "nav", "footer", "noscript", "svg", "header", "aside"}

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.base_host = (urlparse(base_url).netloc or "").lower()
        self._ignore_depth = 0
        self._in_title = False
        self._current_href: str | None = None
        self._current_anchor_parts: list[str] = []
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.outbound_links: list[dict] = []
        self.stock_images: list[str] = []
        self.has_table = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        t = tag.lower()
        if t in self.IGNORED_TAGS:
            self._ignore_depth += 1
            return
        if t == "title":
            self._in_title = True
        if self._ignore_depth > 0:
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if t in ("table", "thead", "tbody"):
            self.has_table = True
        elif t == "img":
            src = attr_map.get("src") or attr_map.get("data-src") or ""
            if src:
                full_src = urljoin(self.base_url, src)
                if any(sd in full_src.lower() for sd in STOCK_DOMAINS):
                    self.stock_images.append(full_src)
        elif t == "a":
            href = attr_map.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                self._current_href = urljoin(self.base_url, href)
                self._current_anchor_parts = []

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t in self.IGNORED_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1
            return
        if t == "title":
            self._in_title = False
        if self._ignore_depth > 0:
            return
        if t == "a" and self._current_href:
            anchor_text = " ".join("".join(self._current_anchor_parts).split())
            url = self._current_href
            parsed = urlparse(url)
            host = (parsed.netloc or "").lower()
            path_lower = (parsed.path or "").lower()
            dom_cat = categorize_domain(url)
            is_doc_ext = any(path_lower.endswith(ext) for ext in PRIMARY_DOC_EXTENSIONS)
            is_external = bool(host and host != self.base_host) or not self.base_host
            is_noisy = _is_noisy_search_or_nav_url(url)
            is_primary_candidate = (
                not is_noisy
                and (is_external or is_doc_ext)
                and dom_cat != "social_or_video"
                and (
                    is_doc_ext
                    or (is_external and dom_cat in ("institutional_gov", "academic_edu"))
                    or any(w in anchor_text.lower() for w in ("pdf", "resolución", "acta", "sentencia", "report", "expediente", "docket", "dataset"))
                )
            )
            if is_external or is_doc_ext:
                self.outbound_links.append({
                    "url": url,
                    "anchor_text": anchor_text[:160],
                    "domain_category": dom_cat,
                    "is_primary_candidate": bool(is_primary_candidate),
                })
            self._current_href = None
            self._current_anchor_parts = []
        elif t in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br"):
            self.text_parts.append("\n")

    def handle_data(self, data: str):
        if self._in_title:
            self.title_parts.append(data)
        if self._ignore_depth > 0:
            return
        if self._current_href is not None:
            self._current_anchor_parts.append(data)
        self.text_parts.append(data)


def extract_html_content(html: str, base_url: str = "") -> dict:
    parser = _CleanHTMLParser(base_url)
    parser.feed(html or "")
    raw_text = "".join(parser.text_parts)
    lines = [" ".join(line.split()) for line in raw_text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)
    seen_urls: set[str] = set()
    dedup_links: list[dict] = []
    for link in parser.outbound_links:
        if link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            dedup_links.append(link)
    return {
        "title": " ".join("".join(parser.title_parts).split()),
        "text": clean_text,
        "outbound_links": dedup_links,
        "stock_images": parser.stock_images,
        "has_table": parser.has_table,
    }


def analyze_document_text(
    text: str,
    url_or_path: str,
    resource_type: str,
    agent_evidence_markers: list[str] | None,
    outbound_links: list[dict] | None,
    stock_images: list[str] | None,
    has_table: bool = False,
    page_count: int = 1,
    max_excerpts: int = 5,
) -> dict:
    clean_text = (text or "").strip()
    markers = [m.strip() for m in (agent_evidence_markers or []) if m and m.strip()]
    links = list(outbound_links or [])
    stocks = list(stock_images or [])
    domain_cat = categorize_domain(url_or_path)

    friction_signals: list[str] = []
    secondary_signals: list[str] = []
    primary_signals: list[str] = []
    reasons: list[str] = []

    if stocks:
        friction_signals.append(f"Contiene {len(stocks)} imagen(es) de bancos de stock ({stocks[0][:80]}).")

    if len(clean_text) < 20:
        friction_signals.append("Documento vacío o sin texto extraíble (text_length < 20).")
        reasons.append("Documento vacío o sin texto legible al cargar la fuente.")
        return {
            "url_or_path": url_or_path,
            "format": resource_type,
            "domain_category": domain_cat,
            "page_count": page_count,
            "preliminary_classification": "unreachable_or_empty",
            "classification_reasons": reasons,
            "secondary_signals": secondary_signals,
            "primary_signals": primary_signals,
            "friction_signals": friction_signals,
            "detected_identifiers": [],
            "matched_excerpts": [],
            "outbound_links": links[:12],
        }

    if clean_text.startswith("[SCANNED_FACSIMILE_PDF:"):
        friction_signals.append(
            "PDF escaneado (facsímil) sin capa de texto OCR; requiere inspección visual de las páginas renderizadas."
        )
        reasons.append(
            "PDF escaneado sin texto extraíble (facsímil sin capa OCR); revisar imágenes renderizadas adjuntas o realizar OCR."
        )
        return {
            "url_or_path": url_or_path,
            "format": resource_type,
            "domain_category": domain_cat,
            "page_count": page_count,
            "preliminary_classification": "unreachable_or_empty",
            "classification_reasons": reasons,
            "secondary_signals": secondary_signals,
            "primary_signals": primary_signals,
            "friction_signals": friction_signals,
            "detected_identifiers": [],
            "matched_excerpts": [{"marker": "scanned_facsimile", "excerpt": clean_text[:240]}],
            "outbound_links": links[:12],
        }

    if len(clean_text) < 2500 and any(re.search(pat, clean_text, flags=re.IGNORECASE) for pat in BOT_CHALLENGE_PATTERNS):
        friction_signals.append(
            "Portal bloqueado por desafío anti-bot, CAPTCHA o requisito de JavaScript/cookies."
        )
        reasons.append(
            "Portal bloqueado por desafío anti-bot o requisito de JavaScript (no entrega el contenido real del documento)."
        )
        return {
            "url_or_path": url_or_path,
            "format": resource_type,
            "domain_category": domain_cat,
            "page_count": page_count,
            "preliminary_classification": "unreachable_or_empty",
            "classification_reasons": reasons,
            "secondary_signals": secondary_signals,
            "primary_signals": primary_signals,
            "friction_signals": friction_signals,
            "detected_identifiers": [],
            "matched_excerpts": [{"marker": "bot_challenge", "excerpt": " ".join(clean_text[:240].split())}],
            "outbound_links": [],
        }

    detected_identifiers = sorted(
        {m.group(1).rstrip(".,;)") for m in DOI_REGEX.finditer(clean_text)}
    )

    paywall_matches: list[str] = []
    for pat in PAYWALL_PATTERNS:
        for m in re.finditer(pat, clean_text, flags=re.IGNORECASE):
            paywall_matches.append(m.group(0).lower())

    url_looks_like_pdf = url_or_path.lower().split("?")[0].endswith(".pdf")
    is_false_pdf_landing = url_looks_like_pdf and resource_type == "html"
    if is_false_pdf_landing or len(set(paywall_matches)) >= 2:
        friction_signals.append(
            "Ficha o resumen restringido tras paywall editorial (no entrega el cuerpo completo del documento)."
        )

    attribution_matches: list[str] = []
    for pat in ATTRIBUTION_PATTERNS:
        for m in re.finditer(pat, clean_text, flags=re.IGNORECASE):
            start = max(0, m.start() - 25)
            end = min(len(clean_text), m.end() + 65)
            snippet = " ".join(clean_text[start:end].split())
            attribution_matches.append(snippet)

    format_matches: list[str] = []
    for pat in SECONDARY_FORMAT_PATTERNS:
        for m in re.finditer(pat, clean_text, flags=re.IGNORECASE):
            format_matches.append(m.group(0))

    if attribution_matches:
        secondary_signals.append(
            f"Detectadas {len(attribution_matches)} expresiones de atribución a terceros (ej.: '{attribution_matches[0]}')."
        )
    if format_matches:
        unique_formats = sorted(set(f.lower() for f in format_matches))
        secondary_signals.append(
            f"Marcadores de formato secundario/resumen detectados: {', '.join(unique_formats)}."
        )

    tabular_lines = sum(1 for line in clean_text.splitlines() if "|" in line or "\t" in line)
    effective_table = bool(has_table or tabular_lines >= 2)
    if effective_table:
        primary_signals.append("Contiene estructura tabular o registros estructurados de datos.")

    matched_excerpts: list[dict] = []
    matched_marker_names: list[str] = []
    for marker in markers:
        idx = clean_text.lower().find(marker.lower())
        if idx != -1:
            matched_marker_names.append(marker)
            if len(matched_excerpts) < max_excerpts:
                start = max(0, idx - 80)
                end = min(len(clean_text), idx + len(marker) + 140)
                matched_excerpts.append({
                    "marker": marker,
                    "excerpt": " ".join(clean_text[start:end].split()),
                })

    if matched_marker_names:
        primary_signals.append(
            f"Coincide con {len(matched_marker_names)} marcador(es) probatorio(s) del tema: {', '.join(matched_marker_names)}."
        )

    primary_candidate_links = [l for l in links if l.get("is_primary_candidate")]
    is_official_or_pdf = resource_type == "pdf" or domain_cat in ("institutional_gov", "academic_edu")
    parsed_host = (urlparse(url_or_path).netloc or "").lower()
    is_encyclopedia = any(h in parsed_host for h in ENCYCLOPEDIA_HOSTS)
    is_bibliographic_stub = (
        resource_type == "html"
        and any(h in parsed_host for h in BIBLIOGRAPHIC_STUB_HOSTS)
        and len(clean_text) < 15000
    )
    is_paywalled_landing = resource_type == "html" and (
        is_false_pdf_landing or len(set(paywall_matches)) >= 2 or is_bibliographic_stub
    )

    if is_paywalled_landing:
        classification = "paywalled_abstract_only"
        id_hint = f" Identificadores extraídos para buscar copia abierta: {', '.join(detected_identifiers)}." if detected_identifiers else ""
        if is_bibliographic_stub and not (is_false_pdf_landing or len(set(paywall_matches)) >= 2):
            friction_signals.append(
                "Ficha o índice bibliográfico (muestra metadatos/resumen, no el texto completo del documento)."
            )
            reasons.append(
                "Ficha o índice bibliográfico (muestra metadatos/abstract pero no el cuerpo ni tablas completas del documento)." + id_hint
            )
        else:
            reasons.append(
                "Ficha bibliográfica o resumen restringido tras paywall editorial (muestra metadatos/abstract pero no el cuerpo ni tablas completas del documento)." + id_hint
            )
    elif is_encyclopedia:
        if len(primary_candidate_links) > 0:
            classification = "secondary_bridge"
            reasons.append(
                f"Enciclopedia o fuente terciaria (ej. Wikipedia); actúa como Fuente Puente porque enlaza a {len(primary_candidate_links)} candidato(s) primario(s)."
            )
        else:
            classification = "secondary_no_outbound_proof"
            reasons.append(
                "Enciclopedia o fuente terciaria sin registro primario propio ni enlaces salientes candidatos verificados."
            )
    elif is_official_or_pdf and (
        len(format_matches) > 0
        or (len(attribution_matches) >= 2 and not effective_table)
    ):
        classification = "official_or_pdf_but_secondary"
        reasons.append(
            "Aunque proviene de un PDF o dominio oficial, presenta formato de comunicado/resumen secundario o síntesis (meta-análisis/revisión) y atribución a terceros sin datos o registros primarios propios."
        )
    elif len(matched_marker_names) > 0 and (effective_table or is_official_or_pdf or resource_type == "dataset") and len(format_matches) == 0:
        classification = "likely_primary"
        reasons.append(
            "Contiene marcadores probatorios directos del tema junto con estructura de registro/tabla o documento fuente sin formato de comunicado secundario."
        )
    elif len(primary_candidate_links) > 0:
        classification = "secondary_bridge"
        reasons.append(
            f"Fuente secundaria (atribución/divulgación), pero actúa como Fuente Puente porque enlaza directamente a {len(primary_candidate_links)} candidato(s) a documento primario."
        )
    else:
        classification = "secondary_no_outbound_proof"
        reasons.append(
            "Fuente secundaria sin registros primarios propios ni enlaces salientes verificables hacia un documento raíz."
        )

    if not matched_excerpts:
        matched_excerpts.append({
            "marker": "lead_excerpt",
            "excerpt": " ".join(clean_text[:240].split()),
        })

    return {
        "url_or_path": url_or_path,
        "format": resource_type,
        "domain_category": domain_cat,
        "page_count": page_count,
        "preliminary_classification": classification,
        "classification_reasons": reasons,
        "secondary_signals": secondary_signals[:5],
        "primary_signals": primary_signals[:5],
        "friction_signals": friction_signals[:5],
        "detected_identifiers": detected_identifiers[:8],
        "matched_excerpts": matched_excerpts[:max_excerpts],
        "outbound_links": (primary_candidate_links + [l for l in links if not l.get("is_primary_candidate")])[:12],
    }


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-záéíóúñü0-9]{3,}", (text or "").lower())
    stopwords = {"para", "como", "este", "esta", "pero", "más", "del", "las", "los", "una", "con", "por", "que", "the", "and", "for", "with", "that", "from"}
    return [w for w in words if w not in stopwords]


def compute_echo_clusters(items: list[dict], similarity_threshold: float = 0.45) -> list[dict]:
    if len(items) < 2:
        return []
    docs_tokens = [_tokenize(item.get("text", "")) for item in items]
    n_docs = len(items)
    df: Counter[str] = Counter()
    for tokens in docs_tokens:
        for term in set(tokens):
            df[term] += 1

    vectors: list[dict[str, float]] = []
    for tokens in docs_tokens:
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        norm_sq = 0.0
        for term, count in tf.items():
            idf = math.log((1.0 + n_docs) / (1.0 + df[term])) + 1.0
            w = count * idf
            vec[term] = w
            norm_sq += w * w
        norm = math.sqrt(norm_sq) or 1.0
        vectors.append({k: v / norm for k, v in vec.items()})

    adj: dict[int, set[int]] = {i: set() for i in range(n_docs)}
    pair_sims: dict[tuple[int, int], float] = {}
    for i in range(n_docs):
        for j in range(i + 1, n_docs):
            v1, v2 = vectors[i], vectors[j]
            if len(v1) > len(v2):
                v1, v2 = v2, v1
            sim = sum(val * v2.get(term, 0.0) for term, val in v1.items())
            if sim >= similarity_threshold:
                adj[i].add(j)
                adj[j].add(i)
                pair_sims[(i, j)] = sim

    visited: set[int] = set()
    clusters: list[dict] = []
    for i in range(n_docs):
        if i in visited or not adj[i]:
            continue
        comp: list[int] = []
        queue = [i]
        visited.add(i)
        while queue:
            curr = queue.pop(0)
            comp.append(curr)
            for nxt in sorted(adj[curr]):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        if len(comp) >= 2:
            sims = [
                pair_sims[(min(a, b), max(a, b))]
                for idx_a, a in enumerate(comp)
                for b in comp[idx_a + 1 :]
                if (min(a, b), max(a, b)) in pair_sims
            ]
            avg_sim = round(sum(sims) / max(len(sims), 1), 3)
            clusters.append({
                "urls": [items[idx]["url"] for idx in comp],
                "average_similarity": avg_sim,
                "reason": f"Clúster de eco detectado: {len(comp)} fuentes comparten alta similitud textual ({avg_sim}).",
            })
    return clusters

# Primary Source Tracer Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir e instalar el plugin local de Antigravity `primary-source-tracer` que combina un servidor MCP en Python 100 % agnóstico al dominio con una skill metodológica para rastrear fuentes primarias, detectar bucles de eco y clasificar explícitamente fuentes secundarias (incluyendo falsos primarios en PDFs y sitios oficiales) con sus razones.

**Architecture:** Un paquete de plugin en `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\` compuesto por: (1) `mcp/analyzer.py` con el motor determinístico de extracción HTML/PDF, detección de atribución secundaria vs. datos propios, extracción de enlaces puente y clustering de eco por TF-IDF en Python puro; (2) `mcp/server.py` que expone 3 herramientas vía JSON-RPC 2.0 sobre `stdio`; y (3) `skills/primary-source-search/SKILL.md` + `rules/AGENTS.md` que guían al agente para definir dinámicamente los términos/marcadores de cada tema y reportar tanto fuentes primarias como secundarias con sus razones.

**Tech Stack:** Python 3 (biblioteca estándar `urllib`, `html.parser`, `re`, `math`, `json`, `collections`, con soporte opcional para `pypdf` / `fitz`), protocolo MCP (`stdio` JSON-RPC 2.0), `pytest` / `unittest`.

**Spec:** `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\docs\superpowers\specs\2026-11-23-primary-source-tracer-design.md`

## Global Constraints

- Ubicación objetivo del plugin instalado: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\`
- 100 % agnóstico al tema: el código del servidor MCP no contiene términos de búsqueda, unidades ni palabras clave de ningún dominio específico.
- Filtro explícito contra fuentes secundarias (incluyendo PDFs y sitios oficiales `.gov`/`.gob`/`.edu`): nunca clasificar como primaria solo por extensión `.pdf` o dominio oficial.
- Transparencia total sin descartes silenciosos: conservar todas las fuentes secundarias evaluadas junto con su subtipo y su `classification_reasons`.
- Presupuesto de contexto (`context-mode`): respuestas de herramientas MCP compactas (<12 KB).
- `plugin.json` válido únicamente con campos soportados (`name`, `displayName`, `description`, `version`, `logo`, `suggestedPrompts`).
- Nombre del servidor MCP prefijado único: `primary-source-tracer`.

## Review Focus

1. **PDF o página `.gov` que es un comunicado de prensa o resumen secundario citando a terceros**: debe clasificarse como `official_or_pdf_but_secondary` con razones explícitas en `classification_reasons`, nunca como `likely_primary`.
2. **Artículo secundario con enlace saliente a un PDF/documento raíz ("Fuente Puente")**: debe clasificarse como `secondary_bridge`, conservar su razón de por qué es secundario y exponer el enlace hacia el documento raíz en `outbound_links`.
3. **Página que carga vacía (`text_length == 0`) o falla por red/timeout**: no debe lanzar una excepción no controlada en el servidor MCP; debe devolver `preliminary_classification: "unreachable_or_empty"` y registrar la fricción en `friction_signals` y `classification_reasons`.
4. **Artículos clonados que repiten la misma nota con mínimas variaciones ("Eco")**: `compute_echo_clusters` debe agruparlos en un mismo clúster sin eliminar ninguno del listado de fuentes evaluadas.
5. **Documento enorme (>100 KB de texto)**: `inspect_and_classify_source` debe truncar y acotar los extractos (`max_excerpts`) para que el payload JSON resultante nunca supere 12 KB.

---

### Task 1: Motor de Análisis, Clasificación y Similitud Agnóstico al Dominio (`mcp/analyzer.py`)

**Files:**
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\__init__.py`
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\analyzer.py`
- Test: `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_analyzer.py`

**Interfaces:**
- Consumes: none (Python stdlib + optional `pypdf`/`fitz`)
- Produces:
  - `categorize_domain(url: str) -> str` (`"institutional_gov"`, `"academic_edu"`, `"media_or_blog"`, `"social_or_video"`, `"other"`)
  - `extract_html_content(html: str, base_url: str) -> dict` (`{"title": str, "text": str, "outbound_links": list[dict], "stock_images": list[str], "has_table": bool}`)
  - `analyze_document_text(text: str, url_or_path: str, resource_type: str, agent_evidence_markers: list[str], outbound_links: list[dict], stock_images: list[str], has_table: bool, page_count: int = 1, max_excerpts: int = 5) -> dict`
  - `compute_echo_clusters(items: list[dict], similarity_threshold: float = 0.45) -> list[dict]`

- [ ] **Step 1: Write the failing unit tests in `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_analyzer.py`**

```python
import sys
from pathlib import Path

PLUGIN_DIR = Path(r"C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer")
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.analyzer import (
    categorize_domain,
    extract_html_content,
    analyze_document_text,
    compute_echo_clusters,
)


def test_official_gov_press_release_classified_as_secondary():
    text = (
        "Comunicado de prensa oficial. Según un estudio publicado por otra entidad, "
        "y de acuerdo con reportes preliminares de prensa, se estima un impacto general. "
        "Press release overview: according to external analysts, figures may vary."
    )
    res = analyze_document_text(
        text=text,
        url_or_path="https://agency.gov/press-release.pdf",
        resource_type="pdf",
        agent_evidence_markers=["Expediente 402", "Tabla 1"],
        outbound_links=[],
        stock_images=[],
        has_table=False,
        page_count=2,
    )
    assert res["preliminary_classification"] == "official_or_pdf_but_secondary"
    assert any("atribución" in r.lower() or "secundario" in r.lower() for r in res["classification_reasons"])


def test_secondary_bridge_detected_when_linking_to_primary_candidate():
    html = """
    <html><head><title>Nota periodística</title></head>
    <body>
      <article>
        <p>Según informaron vecinos y de acuerdo con el reporte oficial, hubo reclamos.</p>
        <img src="https://media.istockphoto.com/photos/server-room.jpg" />
        <a href="https://tribunal.gob.cl/sentencias/resolucion-123.pdf">Ver resolución oficial PDF</a>
        <a href="https://instagram.com/reel/xyz">Ver reel</a>
      </article>
    </body></html>
    """
    parsed = extract_html_content(html, "https://diarioejemplo.com/nota")
    assert len(parsed["stock_images"]) == 1
    res = analyze_document_text(
        text=parsed["text"],
        url_or_path="https://diarioejemplo.com/nota",
        resource_type="html",
        agent_evidence_markers=["Resolución 123"],
        outbound_links=parsed["outbound_links"],
        stock_images=parsed["stock_images"],
        has_table=parsed["has_table"],
    )
    assert res["preliminary_classification"] == "secondary_bridge"
    assert any(l["url"].endswith("resolucion-123.pdf") and l["is_primary_candidate"] for l in res["outbound_links"])
    assert any("stock" in s.lower() for s in res["friction_signals"])


def test_primary_document_with_agent_markers_and_table():
    text = (
        "ACTA OFICIAL N° 88-2025. Registro directo de mediciones en terreno.\n"
        "Punto 1 | Lectura A: 54.2 | Lectura B: 61.8\n"
        "Punto 2 | Lectura A: 58.9 | Lectura B: 65.0\n"
    )
    res = analyze_document_text(
        text=text,
        url_or_path="https://county.gov/records/acta-88.pdf",
        resource_type="pdf",
        agent_evidence_markers=["ACTA OFICIAL", "Lectura A"],
        outbound_links=[],
        stock_images=[],
        has_table=True,
        page_count=4,
    )
    assert res["preliminary_classification"] == "likely_primary"
    assert len(res["matched_excerpts"]) >= 1


def test_empty_document_returns_unreachable_or_empty():
    res = analyze_document_text(
        text="   ",
        url_or_path="https://portalroto.gob.cl/causa",
        resource_type="html",
        agent_evidence_markers=["Causa"],
        outbound_links=[],
        stock_images=[],
        has_table=False,
    )
    assert res["preliminary_classification"] == "unreachable_or_empty"
    assert any("vacío" in r.lower() or "sin texto" in r.lower() for r in res["classification_reasons"])


def test_echo_clusters_group_near_duplicate_articles():
    items = [
        {"url": "https://medio1.com/a", "text": "Cinco palabras del castellano antiguo como toballa y murciégalo cambiaron con la historia del idioma español."},
        {"url": "https://medio2.com/b", "text": "Las 5 palabras del castellano antiguo como toballa y murciégalo que cambiaron en la historia del idioma español."},
        {"url": "https://archivo.org/c", "text": "Catálogo de manuscritos digitales conservados en la biblioteca nacional con signatura MS-1492."},
    ]
    clusters = compute_echo_clusters(items, similarity_threshold=0.45)
    assert len(clusters) == 1
    assert set(clusters[0]["urls"]) == {"https://medio1.com/a", "https://medio2.com/b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp.analyzer'`

- [ ] **Step 3: Implement `mcp/analyzer.py`**

Create `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\__init__.py` and `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\analyzer.py` implementing:
- `STOCK_DOMAINS = ("istockphoto.com", "shutterstock.com", "gettyimages.", "unsplash.com", "freepik.com", "stock.adobe.com", "depositphotos.com")`
- `SOCIAL_DOMAINS = ("instagram.com", "tiktok.com", "facebook.com", "x.com", "twitter.com", "youtube.com", "youtu.be", "reddit.com", "pinterest.")`
- Universal attribution patterns (`ATTRIBUTION_PATTERNS`: `"según "`, `"de acuerdo con"`, `"citado por"`, `"fuente:"`, `"according to"`, `"as reported by"`, `"cited in"`, `"source:"`) and secondary format patterns (`SECONDARY_FORMAT_PATTERNS`: `"comunicado de prensa"`, `"nota de prensa"`, `"boletín"`, `"press release"`, `"fact sheet"`, `"policy brief"`, `"overview"`, `"resumen ejecutivo"`).
- `analyze_document_text(...)` classification rules:
  - If stripped `text` length < 20: `"unreachable_or_empty"`.
  - Count attribution matches, secondary format matches, agent marker matches, and tabular cues (`has_table` or `|` / tab-delimited numeric rows).
  - If `(resource_type == "pdf" or domain_category in ("institutional_gov", "academic_edu"))` AND (`secondary_format_hits > 0` or (`attribution_hits >= 2` and `marker_hits == 0` and not `has_table`)): classify as `"official_or_pdf_but_secondary"` and populate `classification_reasons` explaining why an official/PDF source was downgraded to secondary.
  - Else if `marker_hits > 0` and (`has_table` or `resource_type in ("pdf", "dataset")` or `domain_category in ("institutional_gov", "academic_edu")`) and `secondary_format_hits == 0`: classify as `"likely_primary"`.
  - Else if any outbound link has `is_primary_candidate=True`: classify as `"secondary_bridge"`.
  - Else: classify as `"secondary_no_outbound_proof"`.
- `compute_echo_clusters(items, similarity_threshold=0.45)`: pure-Python TF-IDF cosine similarity over word/character 3-grams; returns list of clusters with `>= 2` URLs and average similarity score.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_analyzer.py -v`
Expected: PASS (5 passed)

---

### Task 2: Servidor MCP Local y Herramientas de Búsqueda/Rastreo (`mcp/server.py`)

**Files:**
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\server.py`
- Test: `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_server.py`

**Interfaces:**
- Consumes: `categorize_domain`, `extract_html_content`, `analyze_document_text`, `compute_echo_clusters` from `mcp.analyzer`
- Produces:
  - `fetch_document(url_or_path: str, timeout: int = 8) -> dict`
  - `tool_search_web_candidates(queries: list[str], max_results_per_query: int = 8) -> dict`
  - `tool_inspect_and_classify_source(url_or_path: str, agent_evidence_markers: list[str] = None, max_excerpts: int = 5) -> dict`
  - `tool_compare_echo_and_trace(urls: list[str], agent_evidence_markers: list[str] = None, follow_bridge_links: bool = True, max_bridge_hops: int = 4) -> dict`
  - `handle_jsonrpc_request(request: dict) -> dict | None` (standard MCP `initialize`, `notifications/initialized`, `tools/list`, `tools/call`)

- [ ] **Step 1: Write the failing unit tests in `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_server.py`**

```python
import json
import sys
from pathlib import Path

PLUGIN_DIR = Path(r"C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer")
sys.path.insert(0, str(PLUGIN_DIR))

from mcp.server import (
    handle_jsonrpc_request,
    tool_inspect_and_classify_source,
    tool_compare_echo_and_trace,
)


def test_mcp_initialize_and_tools_list():
    init_resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_resp["result"]["serverInfo"]["name"] == "primary-source-tracer"

    tools_resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
    assert tool_names == {
        "search_web_candidates",
        "inspect_and_classify_source",
        "compare_echo_and_trace",
    }


def test_inspect_local_file_and_context_budget_cap(tmp_path):
    big_file = tmp_path / "huge_report.html"
    repeated_body = "<p>Según reportes de prensa, este texto se repite. " + ("dato " * 4000) + "</p>"
    big_file.write_text(f"<html><body><article>{repeated_body}</article></body></html>", encoding="utf-8")

    result = tool_inspect_and_classify_source(
        url_or_path=str(big_file),
        agent_evidence_markers=["Expediente X"],
        max_excerpts=3,
    )
    serialized = json.dumps(result, ensure_ascii=False)
    assert len(serialized.encode("utf-8")) < 12288
    assert result["preliminary_classification"] in ("secondary_no_outbound_proof", "official_or_pdf_but_secondary")


def test_compare_echo_and_trace_follows_local_bridge(tmp_path):
    primary_file = tmp_path / "acta_oficial.html"
    primary_file.write_text(
        "<html><body><table><tr><td>ACTA-99</td><td>Medición: 55.4</td></tr></table></body></html>",
        encoding="utf-8",
    )
    bridge_file = tmp_path / "nota_puente.html"
    bridge_file.write_text(
        f'<html><body><article><p>Según vecinos hubo reclamos.</p>'
        f'<a href="{primary_file.as_posix()}">Descargar acta oficial PDF</a></article></body></html>',
        encoding="utf-8",
    )
    clone_file = tmp_path / "nota_clon.html"
    clone_file.write_text(
        '<html><body><article><p>Según vecinos hubo reclamos en la zona.</p></article></body></html>',
        encoding="utf-8",
    )

    trace = tool_compare_echo_and_trace(
        urls=[str(bridge_file), str(clone_file)],
        agent_evidence_markers=["ACTA-99", "55.4"],
        follow_bridge_links=True,
        max_bridge_hops=2,
    )
    assert len(trace["evaluated_sources"]) == 3
    assert len(trace["bridge_paths"]) == 1
    classifications = {Path(s["url_or_path"]).name: s["preliminary_classification"] for s in trace["evaluated_sources"]}
    assert classifications["acta_oficial.html"] == "likely_primary"
    assert classifications["nota_puente.html"] == "secondary_bridge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp.server'`

- [ ] **Step 3: Implement `mcp/server.py`**

Implement `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\server.py` with:
- Local file support (`Path(url_or_path).exists()` or `file://`) and HTTP/HTTPS fetching (`urllib.request.urlopen` with 8s timeout and clean error capture returning empty text + fetch error note on failure).
- PDF text extraction via `pypdf` or `fitz` (PyMuPDF) when installed, plus regex stream fallback so PDFs never crash the server.
- Payload truncation guarantee so serialized JSON returned by each tool is always `< 12 KB`.
- Standard MCP `stdio` loop (`sys.stdin` line-by-line JSON-RPC 2.0 handler).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_server.py -v`
Expected: PASS (3 passed)

---

### Task 3: Empaquetado del Plugin, Skill Metodológica y Verificación (`plugin.json`, `mcp_config.json`, `SKILL.md`, `AGENTS.md`)

**Files:**
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\plugin.json`
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp_config.json`
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\assets\logo.svg`
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\skills\primary-source-search\SKILL.md`
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\rules\AGENTS.md`
- Create: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\README.md`
- Test: `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_plugin_bundle.py`

**Interfaces:**
- Consumes: `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\mcp\server.py`
- Produces: Complete Antigravity plugin bundle at `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\`

- [ ] **Step 1: Write the failing bundle verification test in `C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_plugin_bundle.py`**

```python
import json
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(r"C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer")
ALLOWED_PLUGIN_KEYS = {
    "name", "description", "logo", "suggestedPrompts",
    "displayName", "version", "author", "homepage", "repository", "disabled"
}


def test_plugin_json_and_mcp_config_valid():
    plugin_json = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert plugin_json["name"] == "primary-source-tracer"
    assert set(plugin_json.keys()).issubset(ALLOWED_PLUGIN_KEYS)
    assert (PLUGIN_DIR / plugin_json["logo"]).exists()

    mcp_cfg = json.loads((PLUGIN_DIR / "mcp_config.json").read_text(encoding="utf-8"))
    assert "primary-source-tracer" in mcp_cfg["mcpServers"]


def test_skill_and_rules_enforce_domain_agnostic_and_secondary_listing():
    skill_md = (PLUGIN_DIR / "skills" / "primary-source-search" / "SKILL.md").read_text(encoding="utf-8")
    assert "agent_evidence_markers" in skill_md
    assert "official_or_pdf_but_secondary" in skill_md
    assert "Fuentes Secundarias" in skill_md

    rules_md = (PLUGIN_DIR / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert not rules_md.lstrip().startswith("---")


def test_mcp_server_stdio_subprocess_roundtrip():
    proc = subprocess.Popen(
        [sys.executable, str(PLUGIN_DIR / "mcp" / "server.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    out, err = proc.communicate(
        input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
        timeout=5,
    )
    resp = json.loads(out.strip().splitlines()[0])
    assert len(resp["result"]["tools"]) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests\test_plugin_bundle.py -v`
Expected: FAIL with `FileNotFoundError` for `plugin.json`

- [ ] **Step 3: Create the plugin manifest, MCP config, SVG logo, Skill, Rule, and README**

Create:
1. `plugin.json` with `"name": "primary-source-tracer"`, `"displayName": "Primary Source Tracer"`, `"description"`, `"version": "0.1.0"`, `"logo": "assets/logo.svg"`, and 3 `"suggestedPrompts"`.
2. `mcp_config.json` defining `"primary-source-tracer"` launching `python` with `C:/Users/felipe-pc/.gemini/config/plugins/primary-source-tracer/mcp/server.py`.
3. `assets/logo.svg` (square `128x128` SVG with 10% margin and high contrast).
4. `skills/primary-source-search/SKILL.md` with the 4-phase workflow (Phase 1: Dynamic domain discernment & queries/markers by the agent; Phase 2: Hybrid search & `inspect_and_classify_source` including false-primary PDF/`.gov` filtering; Phase 3: Link-hopping via `compare_echo_and_trace`; Phase 4: Mandatory report sections listing Primary Evidence, Compiled/2nd-order Official Sources, **all Secondary Sources with explicit classification reason**, and Search Metrics).
5. `rules/AGENTS.md` (plain markdown without YAML frontmatter) reminding the agent to activate `primary-source-search` when asked for primary evidence or source verification.
6. `README.md` with user-facing documentation.

- [ ] **Step 4: Run the full test suite to verify everything passes**

Run: `python -m pytest C:\Users\felipe-pc\.gemini\antigravity\scratch\primary-source-tracer\tests -v`
Expected: PASS (all 11 tests across `test_analyzer.py`, `test_server.py`, and `test_plugin_bundle.py` pass)

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primary_source_tracer.analyzer import (
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


def test_paywalled_landing_page_classified_and_extracts_doi():
    text = (
        "About this article. Cite this article: Author, A. Study title. Journal 10, 100 (1999). "
        "https://doi.org/10.1038/365611a0 Access options: Buy article PDF or Institutional Login / Subscribe to journal."
    )
    res = analyze_document_text(
        text=text,
        url_or_path="https://www.publisher.com/articles/365611a0.pdf",
        resource_type="html",
        agent_evidence_markers=["Study title"],
        outbound_links=[],
        stock_images=[],
        has_table=False,
    )
    assert res["preliminary_classification"] == "paywalled_abstract_only"
    assert "10.1038/365611a0" in res.get("detected_identifiers", [])
    assert any("paywall" in r.lower() or "restringid" in r.lower() for r in res["classification_reasons"])


def test_pubmed_stub_not_likely_primary_and_search_links_ignored():
    html = """
    <html><body>
      <article>
        <p>PMID: 8413624. Music and spatial task performance. Rauscher FH, Shaw GL, Ky KN.</p>
        <a href="https://pubmed.ncbi.nlm.nih.gov/?term=Rauscher+FH%5BAuthor%5D">Rauscher FH</a>
        <a href="https://pubmed.ncbi.nlm.nih.gov/help/">NCBI Help</a>
        <a href="https://www.nature.com/articles/365611a0.pdf">Full text PDF</a>
      </article>
    </body></html>
    """
    parsed = extract_html_content(html, "https://pubmed.ncbi.nlm.nih.gov/8413624/")
    cand_urls = {l["url"] for l in parsed["outbound_links"] if l["is_primary_candidate"]}
    assert "https://pubmed.ncbi.nlm.nih.gov/?term=Rauscher+FH%5BAuthor%5D" not in cand_urls
    assert "https://pubmed.ncbi.nlm.nih.gov/help/" not in cand_urls
    assert "https://www.nature.com/articles/365611a0.pdf" in cand_urls

    res = analyze_document_text(
        text=parsed["text"],
        url_or_path="https://pubmed.ncbi.nlm.nih.gov/8413624/",
        resource_type="html",
        agent_evidence_markers=["Rauscher", "spatial task"],
        outbound_links=parsed["outbound_links"],
        stock_images=[],
        has_table=True,
    )
    assert res["preliminary_classification"] == "paywalled_abstract_only"
    assert any("bibliográfic" in r.lower() for r in res["classification_reasons"])


def test_scanned_facsimile_not_classified_as_secondary():
    res = analyze_document_text(
        text="[SCANNED_FACSIMILE_PDF: 1 página(s) con 1 imagen(es) escaneada(s) sin capa OCR; renderizado PNG local omitido en modo remoto]",
        url_or_path="https://example.edu/Rauscher_1993.pdf",
        resource_type="pdf",
        agent_evidence_markers=["Mozart"],
        outbound_links=[],
        stock_images=[],
    )
    assert res["preliminary_classification"] == "unreachable_or_empty"
    assert any("escaneado" in r.lower() or "ocr" in r.lower() for r in res["classification_reasons"])


def test_wikipedia_with_tables_and_meta_analysis_not_likely_primary():
    wiki_res = analyze_document_text(
        text="Mozart effect entry with table data and citations.",
        url_or_path="https://en.wikipedia.org/wiki/Mozart_effect",
        resource_type="html",
        agent_evidence_markers=["Mozart effect"],
        outbound_links=[
            {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1281386/",
                "anchor_text": "Full text PDF",
                "domain_category": "institutional_gov",
                "is_primary_candidate": True,
            }
        ],
        stock_images=[],
        has_table=True,
    )
    assert wiki_res["preliminary_classification"] == "secondary_bridge"

    meta_res = analyze_document_text(
        text="A multiverse meta-analysis of the Mozart effect across 39 studies.",
        url_or_path="https://university.edu/studies/meta.pdf",
        resource_type="pdf",
        agent_evidence_markers=["Mozart effect"],
        outbound_links=[],
        stock_images=[],
        has_table=True,
    )
    assert meta_res["preliminary_classification"] == "official_or_pdf_but_secondary"


def test_bot_challenge_page_classified_unreachable():
    res = analyze_document_text(
        text="Client Challenge. Please enable JavaScript and cookies to continue.",
        url_or_path="https://www.jstor.org/stable/3333640",
        resource_type="html",
        agent_evidence_markers=["Mozart"],
        outbound_links=[
            {
                "url": "https://www.jstor.org/privacy",
                "anchor_text": "Privacy",
                "domain_category": "other",
                "is_primary_candidate": False,
            }
        ],
        stock_images=[],
    )
    assert res["preliminary_classification"] == "unreachable_or_empty"
    assert res["outbound_links"] == []
    assert any("anti-bot" in r.lower() or "javascript" in r.lower() for r in res["classification_reasons"])


class TestAnalyzer(unittest.TestCase):
    def test_1(self):
        test_official_gov_press_release_classified_as_secondary()

    def test_2(self):
        test_secondary_bridge_detected_when_linking_to_primary_candidate()

    def test_3(self):
        test_primary_document_with_agent_markers_and_table()

    def test_4(self):
        test_empty_document_returns_unreachable_or_empty()

    def test_5(self):
        test_echo_clusters_group_near_duplicate_articles()

    def test_6_paywall(self):
        test_paywalled_landing_page_classified_and_extracts_doi()

    def test_7_pubmed_stub_and_noisy_links(self):
        test_pubmed_stub_not_likely_primary_and_search_links_ignored()

    def test_8_scanned_facsimile_classification(self):
        test_scanned_facsimile_not_classified_as_secondary()

    def test_9_wikipedia_and_meta_analysis_classification(self):
        test_wikipedia_with_tables_and_meta_analysis_not_likely_primary()

    def test_10_bot_challenge_classification(self):
        test_bot_challenge_page_classified_unreachable()


if __name__ == "__main__":
    unittest.main()

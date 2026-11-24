import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primary_source_tracer.server import (
    _extract_pdf_bytes,
    _select_relevant_bridge_links,
    handle_jsonrpc_request,
    tool_inspect_and_classify_source,
    tool_compare_echo_and_trace,
    tool_search_web_candidates,
    parse_openalex_work,
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


def test_inspect_local_file_and_context_budget_cap(tmp_path: Path):
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


def test_compare_echo_and_trace_follows_local_bridge(tmp_path: Path):
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


class TestServer(unittest.TestCase):
    def test_1_mcp_protocol(self):
        test_mcp_initialize_and_tools_list()

    def test_2_budget_cap(self):
        with tempfile.TemporaryDirectory() as d:
            test_inspect_local_file_and_context_budget_cap(Path(d))

    def test_3_bridge_and_echo(self):
        with tempfile.TemporaryDirectory() as d:
            test_compare_echo_and_trace_follows_local_bridge(Path(d))

    def test_4_scanned_pdf_renders_png_pages_without_browser(self):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        with tempfile.TemporaryDirectory() as d:
            pdf_path = Path(d) / "scanned_only.pdf"
            doc = fitz.open()
            page = doc.new_page(width=200, height=200)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60), False)
            pix.set_rect(pix.irect, (200, 200, 200))
            page.insert_image(fitz.Rect(20, 20, 120, 120), pixmap=pix)
            doc.save(str(pdf_path))
            doc.close()

            res = tool_inspect_and_classify_source(str(pdf_path), ["Marcador"])
            assert "rendered_page_images" in res
            assert len(res["rendered_page_images"]) == 1
            assert Path(res["rendered_page_images"][0]).exists()

    def test_5_parse_openalex_work_extracts_oa_pdf_and_abstract(self):
        sample_payload = {
            "title": "Music and spatial task performance",
            "publication_year": 1993,
            "cited_by_count": 1420,
            "open_access": {
                "is_oa": True,
                "oa_url": "https://www.uwosh.edu/psychology/Rauscher_Shaw-Ky_1993.pdf",
            },
            "authorships": [
                {"author": {"display_name": "Frances H. Rauscher"}},
                {"author": {"display_name": "Gordon L. Shaw"}},
            ],
            "abstract_inverted_index": {
                "Listening": [0],
                "to": [1],
                "Mozart": [2],
                "temporarily": [3],
                "improved": [4],
                "spatial": [5],
                "scores.": [6],
            },
        }
        parsed = parse_openalex_work(sample_payload)
        assert parsed["oa_pdf_url"] == "https://www.uwosh.edu/psychology/Rauscher_Shaw-Ky_1993.pdf"
        assert parsed["abstract_text"] == "Listening to Mozart temporarily improved spatial scores."
        assert "Frances H. Rauscher" in parsed["authors"]
        assert parsed["cited_by_count"] == 1420

    def test_6_remote_scanned_pdf_emits_inline_mcp_image_blocks(self):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60), False)
        pix.set_rect(pix.irect, (200, 200, 200))
        page.insert_image(fitz.Rect(20, 20, 120, 120), pixmap=pix)
        pdf_bytes = doc.tobytes()
        doc.close()

        text, count, paths, inline_imgs = _extract_pdf_bytes(
            pdf_bytes,
            render_images=False,
            render_base64=True,
        )
        assert count == 1
        assert paths == []
        assert len(inline_imgs) == 1
        assert inline_imgs[0]["mimeType"] == "image/jpeg"

        fake_fetched = {
            "title": "scan.pdf",
            "text": text,
            "resource_type": "pdf",
            "outbound_links": [],
            "stock_images": [],
            "has_table": False,
            "page_count": count,
            "rendered_page_images": [],
            "inline_images": inline_imgs,
            "error": None,
        }
        with patch("primary_source_tracer.server.fetch_document", return_value=fake_fetched):
            resp = handle_jsonrpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {
                        "name": "inspect_and_classify_source",
                        "arguments": {"url_or_path": "https://example.edu/scan.pdf"},
                    },
                },
                remote_safe=True,
            )
        blocks = resp["result"]["content"]
        assert blocks[0]["type"] == "text"
        parsed_json = json.loads(blocks[0]["text"])
        assert parsed_json["preliminary_classification"] == "unreachable_or_empty"
        assert parsed_json["inline_images_attached"] == 1
        assert "_inline_images" not in parsed_json
        assert len(blocks) == 2
        assert blocks[1]["type"] == "image"
        assert blocks[1]["mimeType"] == "image/jpeg"

    def test_7_search_web_candidates_falls_back_when_ddg_blocked(self):
        with (
            patch(
                "primary_source_tracer.server._search_duckduckgo",
                return_value=([], "DuckDuckGo devolvió desafío anti-bot HTTP 202"),
            ),
            patch(
                "primary_source_tracer.server._search_openalex_candidates",
                return_value=[
                    {
                        "query_used": "Mozart effect",
                        "title": "Music and spatial task performance",
                        "url": "https://doi.org/10.1038/365611a0",
                        "snippet": "DOI/Registro OpenAlex (1993, 1420 citas).",
                        "search_engine": "openalex",
                    }
                ],
            ),
            patch(
                "primary_source_tracer.server._search_wikipedia_candidates",
                return_value=[
                    {
                        "query_used": "Mozart effect",
                        "title": "[Wikipedia EN] Mozart effect",
                        "url": "https://en.wikipedia.org/wiki/Mozart_effect",
                        "snippet": "The Mozart effect is a set of research results...",
                        "search_engine": "wikipedia_en",
                    }
                ],
            ),
        ):
            res = tool_search_web_candidates(["Mozart effect"], max_results_per_query=5)
        assert res["total_candidates"] == 2
        assert any("202" in msg for msg in res.get("search_friction", []))
        engines = {c["search_engine"] for c in res["candidates"]}
        assert engines == {"openalex", "wikipedia_en"}

    def test_8_bridge_relevance_filters_unrelated_giant_list_links(self):
        src = {
            "url_or_path": "https://en.wikipedia.org/wiki/List_of_common_misconceptions",
            "outbound_links": [
                {
                    "url": "https://www.treasury.gov/currency/history",
                    "anchor_text": "US Treasury currency",
                    "is_primary_candidate": True,
                },
                {
                    "url": "https://www.federalreserve.gov/notes",
                    "anchor_text": "Federal Reserve bank notes",
                    "is_primary_candidate": True,
                },
                {
                    "url": "https://www.nasa.gov/moon",
                    "anchor_text": "NASA Moon landing",
                    "is_primary_candidate": True,
                },
                {
                    "url": "https://www.noaa.gov/weather",
                    "anchor_text": "NOAA weather",
                    "is_primary_candidate": True,
                },
                {
                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1281386/",
                    "anchor_text": "Rauscher Mozart spatial reasoning study",
                    "is_primary_candidate": True,
                },
            ],
        }
        selected = _select_relevant_bridge_links(src, ["Rauscher", "Mozart", "spatial"])
        assert len(selected) == 1
        assert selected[0]["url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC1281386/"

        no_match_src = dict(src)
        no_match_src["outbound_links"] = src["outbound_links"] + [
            {
                "url": "https://www.cdc.gov/flu",
                "anchor_text": "CDC flu info",
                "is_primary_candidate": True,
            }
        ]
        selected_none = _select_relevant_bridge_links(no_match_src, ["UnrelatedMarkerXYZ"])
        assert selected_none == []


if __name__ == "__main__":
    unittest.main()

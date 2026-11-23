import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primary_source_tracer.server import (
    handle_jsonrpc_request,
    tool_inspect_and_classify_source,
    tool_compare_echo_and_trace,
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


if __name__ == "__main__":
    unittest.main()

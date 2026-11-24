import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primary_source_tracer.analyzer import extract_html_content
from primary_source_tracer.audiovisual import (
    extract_urls_from_text,
    extract_youtube_video_id,
    format_timestamp_mmss,
    prepare_image_mcp_block,
)
from primary_source_tracer.server import handle_jsonrpc_request, tool_inspect_and_classify_source

# Minimal valid 1x1 PNG bytes
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestAudiovisualSupport(unittest.TestCase):
    def test_1_youtube_video_id_extraction(self):
        self.assertEqual(extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ?t=42"), "dQw4w9WgXcQ")
        self.assertEqual(extract_youtube_video_id("https://m.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_youtube_video_id("https://youtube.com/live/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertIsNone(extract_youtube_video_id("https://example.org/watch?v=dQw4w9WgXcQ"))
        self.assertEqual(format_timestamp_mmss(75), "01:15")
        self.assertEqual(format_timestamp_mmss(3665), "01:01:05")

    def test_2_extract_urls_from_youtube_description(self):
        desc = (
            "Fuentes citadas en la entrevista:\n"
            "Estudio original: https://arxiv.org/pdf/2304.03271.pdf\n"
            "DOI: https://doi.org/10.1038/365611a0.\n"
            "Instagram: https://instagram.com/canal"
        )
        links = extract_urls_from_text(desc)
        primary_urls = {l["url"] for l in links if l["is_primary_candidate"]}
        self.assertIn("https://arxiv.org/pdf/2304.03271.pdf", primary_urls)
        self.assertIn("https://doi.org/10.1038/365611a0", primary_urls)
        self.assertNotIn("https://instagram.com/canal", primary_urls)

    def test_3_html_extracts_content_images_filtering_stock_and_icons(self):
        html = """
        <html><body><article>
          <img src="https://media.istockphoto.com/photo/stock.jpg" alt="stock" />
          <img src="https://site.org/assets/icon-menu.svg" alt="menu" />
          <img src="https://site.org/static/avatar-user.png" alt="avatar" />
          <img src="https://site.org/charts/water-table-1.png" alt="Tabla 1 consumo de agua" />
        </article></body></html>
        """
        parsed = extract_html_content(html, "https://site.org/report")
        self.assertEqual(len(parsed["stock_images"]), 1)
        self.assertEqual(len(parsed["content_images"]), 1)
        self.assertEqual(parsed["content_images"][0]["url"], "https://site.org/charts/water-table-1.png")
        self.assertIn("Tabla 1", parsed["content_images"][0]["alt"])

    def test_4_direct_image_inspection_returns_mcp_image_block(self):
        block = prepare_image_mcp_block(TINY_PNG, content_type="image/png", url_or_path="chart.png")
        self.assertIsNotNone(block)
        self.assertEqual(block["mimeType"], "image/png")

        with tempfile.TemporaryDirectory() as d:
            img_path = Path(d) / "acta_grafica.png"
            img_path.write_bytes(TINY_PNG)
            resp = handle_jsonrpc_request({
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "inspect_and_classify_source",
                    "arguments": {"url_or_path": str(img_path)},
                },
            })
        blocks = resp["result"]["content"]
        self.assertEqual(len(blocks), 2)
        payload = json.loads(blocks[0]["text"])
        self.assertEqual(payload["preliminary_classification"], "visual_media_requires_inspection")
        self.assertEqual(payload["inline_images_attached"], 1)
        self.assertEqual(blocks[1]["type"], "image")
        self.assertEqual(blocks[1]["mimeType"], "image/png")

    def test_5_youtube_transcript_attaches_clickable_timestamp_urls(self):
        fake_yt = {
            "title": "Entrevista con investigadora original",
            "text": (
                "Video de YouTube: Entrevista con investigadora original | Canal: Ciencia Directa\n\n"
                "Transcripción con marcas de tiempo:\n"
                "[01:15] En nuestra medición original usamos 36 estudiantes y medimos razonamiento espacial."
            ),
            "resource_type": "video",
            "outbound_links": [
                {
                    "url": "https://arxiv.org/pdf/2304.03271.pdf",
                    "anchor_text": "[Enlace en descripción del video]",
                    "domain_category": "academic_edu",
                    "is_primary_candidate": True,
                }
            ],
            "stock_images": [],
            "content_images": [],
            "has_table": False,
            "page_count": 1,
            "rendered_page_images": [],
            "inline_images": [],
            "media_metadata": {
                "platform": "youtube",
                "video_id": "dQw4w9WgXcQ",
                "channel": "Ciencia Directa",
                "canonical_url": "https://youtu.be/dQw4w9WgXcQ",
                "transcript_type": "manual",
                "transcript_segments": 1,
            },
            "error": None,
        }
        with patch("primary_source_tracer.server.fetch_youtube_source", return_value=fake_yt):
            res = tool_inspect_and_classify_source(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                agent_evidence_markers=["36 estudiantes", "razonamiento espacial"],
                remote_safe=True,
            )
        self.assertEqual(res["media_metadata"]["video_id"], "dQw4w9WgXcQ")
        self.assertTrue(
            any(ex.get("timestamp_url") == "https://youtu.be/dQw4w9WgXcQ?t=75" for ex in res["matched_excerpts"])
        )


if __name__ == "__main__":
    unittest.main()

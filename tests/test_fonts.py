import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from opensiddur_infra.fonts import covers, embed_html_fonts, inventory


class FontTests(unittest.TestCase):
    def test_html_embeds_custom_families_and_uses_the_first_available_face_size(self):
        fonts = {
            "latin": SimpleNamespace(
                names=["Missing", "Installed Latin"],
                entries=[
                    SimpleNamespace(name="Missing", normal_size=99),
                    SimpleNamespace(name="Installed Latin", normal_size=12),
                ],
            ),
            "hebrew": SimpleNamespace(
                names=["Installed Hebrew"],
                entries=[SimpleNamespace(name="Installed Hebrew", normal_size=16)],
            ),
            "display": SimpleNamespace(
                names=["Installed Display"],
                entries=[SimpleNamespace(name="Installed Display", normal_size=20)],
            ),
        }
        typography = SimpleNamespace(
            fonts=fonts,
            page=SimpleNamespace(base_font_size=SimpleNamespace(value="11pt")),
        )
        modules = {
            "opensiddur.exporter.cli_common": SimpleNamespace(
                load_output_settings=lambda *args, **kwargs: SimpleNamespace(
                    typography=typography
                )
            ),
            "opensiddur.exporter.html.css": SimpleNamespace(css_string=json.dumps),
        }

        def match(command, **kwargs):
            name = command[-1]
            return f"/usr/share/fonts/synthetic/{name}.ttf\t{name}"

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "book.html"
            output.write_text("<html><head></head><body>Text</body></html>")
            notices = Path(directory) / "notices.json"
            notices.write_text(json.dumps({"components": [
                {"name": "fonts-synthetic", "text": "Keep <font license>"},
                {"name": "unrelated", "text": "Unrelated component"},
            ]}))
            with (
                patch.dict("sys.modules", modules),
                patch(
                    "opensiddur_infra.fonts.subprocess.check_output", side_effect=match
                ),
                patch("opensiddur_infra.fonts.Path.is_file", return_value=True),
                patch(
                    "opensiddur_infra.fonts.Path.read_bytes",
                    return_value=b"synthetic-font",
                ),
            ):
                embed_html_fonts(
                    output,
                    Path(directory) / "settings.yaml",
                    {
                        "installed": [
                            "Installed Latin",
                            "Installed Hebrew",
                            "Installed Display",
                        ],
                    },
                    notices,
                )
            html = output.read_text()
        self.assertEqual(html.count("@font-face"), 3)
        for name, size in (("latin", 12), ("hebrew", 16), ("display", 20)):
            self.assertIn(f"--normal-{name}: {size}pt;", html)
        self.assertNotIn("99pt", html)
        self.assertIn("Keep &lt;font license&gt;", html)
        self.assertNotIn("Unrelated component", html)

    def test_cmap_ranges_cover_all_required_characters(self):
        self.assertTrue(covers("20-7e 590-5ff", {65, 0x05D0, 0x05AF}))
        self.assertFalse(covers("20-7e 5d0-5ea", {0x05D0, 0x05B0}))

    def test_chooser_uses_resolved_faces_and_respects_pack_support_limits(self):
        root = "/usr/share/fonts/opensiddur-pack/"
        faces = {
            "Full Hebrew": (
                root + "Hebrew Letters with Vowels and Cantillation/full.ttf",
                "590-5ff",
            ),
            "Vowel Hebrew": (
                root + "Hebrew Letters with Vowels (no cantillation)/vowels.ttf",
                "590-5ff",
            ),
            "Plain Hebrew": (root + "Hebrew Letters only/plain.ttf", "590-5ff"),
            "Partial Hebrew": (root + "Hebrew Letters only/partial.ttf", "5d0-5da"),
            "DejaVu Sans": ("/usr/share/fonts/standard/latin.ttf", "20-7e"),
            "Not usable": ("/usr/share/fonts/missing.ttf", "20-7e"),
        }
        rows = "".join(
            f"{file}\t{name}\t{charset}\n" for name, (file, charset) in faces.items()
        )

        def run(command, **kwargs):
            if command[0] == "fc-list":
                return rows
            family = command[-1]
            if family == "Not usable":
                return "/usr/share/fonts/standard/latin.ttf\tDejaVu Sans\t20-7e\n"
            file, charset = faces[family]
            return f"{file}\t{family}\t{charset}\n"

        with (
            patch("opensiddur_infra.fonts.subprocess.check_output", side_effect=run),
            patch("opensiddur_infra.fonts.Path.is_file", return_value=True),
        ):
            catalog = inventory()
        self.assertNotIn("Not usable", catalog["installed"])
        self.assertEqual(
            [g["fonts"] for g in catalog["hebrew"]],
            [["Full Hebrew"], ["Vowel Hebrew"], ["Plain Hebrew"], ["Partial Hebrew"]],
        )
        self.assertEqual(catalog["latin"][0]["fonts"], ["DejaVu Sans"])

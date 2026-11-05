import unittest
from unittest.mock import patch

from opensiddur_infra.fonts import covers, inventory


class FontTests(unittest.TestCase):
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

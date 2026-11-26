import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "notices", Path(__file__).resolve().parents[1] / "scripts" / "notices.py"
)
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


class DistributionTests(unittest.TestCase):
    def os_release(self, text):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "os-release"
        path.write_text(text)
        return path

    def test_ubuntu_packages_link_to_ubuntu(self):
        path = self.os_release(
            'PRETTY_NAME="Ubuntu 26.04 LTS"\nID=ubuntu\nVERSION_ID="26.04"\n'
        )
        system, packages, licenses = notices.system_distribution(path)
        self.assertEqual(system, "Ubuntu")
        self.assertEqual(packages, "https://packages.ubuntu.com/")
        self.assertIn("ubuntu.com", licenses)

    def test_debian_packages_link_to_debian(self):
        path = self.os_release('ID="debian"\nVERSION_CODENAME=trixie\n')
        self.assertEqual(notices.system_distribution(path)[0], "Debian")

    def test_an_unreadable_os_release_falls_back_to_debian(self):
        missing = Path(tempfile.gettempdir()) / "no-such-dir-for-notices" / "os-release"
        self.assertEqual(notices.system_distribution(missing)[0], "Debian")

    def test_an_unknown_distribution_falls_back_to_debian(self):
        path = self.os_release("ID=alpine\n")
        self.assertEqual(notices.system_distribution(path)[0], "Debian")

    def test_single_quoted_ids_are_read(self):
        path = self.os_release("ID='ubuntu'\n")
        self.assertEqual(notices.system_distribution(path)[0], "Ubuntu")

    def test_generate_links_package_notices_to_the_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, processor = root / "bundle", root / "processor"
            docs, common = root / "doc", root / "common-licenses"
            for path in (bundle, processor, docs / "fonts-culmus", common):
                path.mkdir(parents=True)
            (bundle / "release.json").write_text(
                json.dumps({"release": "r1", "processor": "abc"})
            )
            (processor / "LICENSE").write_text("licence")
            (docs / "fonts-culmus" / "copyright").write_text("Culmus copyright")
            (common / "GPL-2").write_text("GPL text")
            result = notices.generate(
                bundle,
                processor,
                os_release=self.os_release("ID=ubuntu\n"),
                package_docs=docs,
                common=common,
            )
        by_name = {c["name"]: c for c in result["components"]}
        self.assertEqual(
            by_name["fonts-culmus"]["source"],
            "https://packages.ubuntu.com/fonts-culmus",
        )
        self.assertEqual(
            by_name["fonts-culmus"]["license"],
            "See Ubuntu copyright and license notices",
        )
        self.assertEqual(by_name["fonts-culmus"]["text"], "Culmus copyright")
        self.assertEqual(
            by_name["GPL-2"]["source"], "https://packages.ubuntu.com/base-files"
        )

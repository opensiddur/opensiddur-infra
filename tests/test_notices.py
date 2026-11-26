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

    def test_generate_names_the_distribution_in_package_notices(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            processor = Path(directory) / "processor"
            bundle.mkdir()
            processor.mkdir()
            (bundle / "release.json").write_text(
                json.dumps({"release": "r1", "processor": "abc"})
            )
            (processor / "LICENSE").write_text("licence")
            path = self.os_release("ID=ubuntu\n")
            result = notices.generate(bundle, processor, os_release=path)
        packages = [
            c for c in result["components"] if c["version"] == "container package"
        ]
        for component in packages:
            self.assertTrue(
                component["source"].startswith("https://packages.ubuntu.com/")
            )
            self.assertEqual(
                component["license"], "See Ubuntu copyright and license notices"
            )

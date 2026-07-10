import pathlib
import tempfile
import unittest
from unittest import mock
import urllib.error

from scripts import fetch_assets


class FetchAssetsTests(unittest.TestCase):
    @mock.patch("scripts.fetch_assets.urllib.request.urlopen", side_effect=urllib.error.URLError("offline"))
    def test_fetch_failure_is_fatal(self, _urlopen):
        with self.assertRaises(RuntimeError):
            fetch_assets.fetch("https://example.invalid/rules", attempts=1)

    def test_abp_domain_conversion(self):
        self.assertEqual(
            "DOMAIN-SUFFIX,example.com",
            fetch_assets.parse_abp_domain_rule("||example.com^"),
        )

    def test_ip_processing_is_canonical(self):
        output = fetch_assets.process_ip("192.0.2.0/24\n")
        self.assertIn("IP-CIDR,192.0.2.0/24,no-resolve", output)
        with self.assertRaises(ValueError):
            fetch_assets.process_ip("192.0.2.1/24\n")

    def test_gfwlist_uses_separate_manual_source(self):
        with tempfile.TemporaryDirectory() as directory:
            manual = pathlib.Path(directory) / "manual.list"
            manual.write_text("DOMAIN-SUFFIX,manual.example\n", encoding="utf-8")
            raw = "[AutoProxy 0.2.9]\n||synced.example\n"
            output = fetch_assets.process_gfwlist(raw, manual)
            self.assertIn("DOMAIN-SUFFIX,manual.example", output)
            self.assertIn("DOMAIN-SUFFIX,synced.example", output)


if __name__ == "__main__":
    unittest.main()

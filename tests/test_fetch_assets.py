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

    def test_wildcard_domain_lines_become_suffix_rules(self):
        content = "# comment\n*.tracker.example\nplain.example\n\n*.bad_value.example\n"

        rules = fetch_assets.process_domain_lines(content)

        self.assertEqual(
            rules,
            {"DOMAIN-SUFFIX,tracker.example", "DOMAIN-SUFFIX,plain.example"},
        )

    def test_clash_list_keeps_supported_tokens_and_canonicalises_cidr(self):
        content = (
            "# NAME: Example\n"
            "DOMAIN,Example.COM\n"
            "DOMAIN-SUFFIX,foo.example\n"
            "DOMAIN-KEYWORD,paypal\n"
            "IP-CIDR,8.8.8.9/24\n"
            "IP-CIDR6,2400:cb00::1/32,no-resolve\n"
            "IP-CIDR,10.0.0.0/8\n"
            "PROCESS-NAME,example\n"
            "URL-REGEX,^https://example\n"
        )

        rules = fetch_assets.process_clash_rule_list(content, "TEST")

        self.assertEqual(
            rules,
            {
                "DOMAIN,example.com",
                "DOMAIN-SUFFIX,foo.example",
                "DOMAIN-KEYWORD,paypal",
                "IP-CIDR,8.8.8.0/24",
                "IP-CIDR6,2400:cb00::/32,no-resolve",
            },
        )

    def test_bundle_merges_sources_and_records_provenance(self):
        bundle = {"label": "示例清单", "converter": "domains", "sources": ("A", "B")}
        fetched = {"A": "*.one.example\n", "B": "one.example\ntwo.example\n"}
        with mock.patch.object(fetch_assets, "SOURCES", {"A": "https://a.example/list", "B": "https://b.example/list"}):
            output = fetch_assets.process_bundle(bundle, fetched)

        self.assertIn("# 内容：示例清单", output)
        self.assertIn("# 数量：2条", output)
        self.assertIn("https://a.example/list", output)
        self.assertIn("DOMAIN-SUFFIX,one.example", output)
        self.assertIn("DOMAIN-SUFFIX,two.example", output)

    def test_every_bundle_source_is_declared(self):
        for relative, bundle in fetch_assets.BUNDLES.items():
            self.assertIn(bundle["converter"], {"domains", "clash"}, relative)
            for source_key in bundle["sources"]:
                self.assertIn(source_key, fetch_assets.SOURCES, relative)

    def test_committed_bundles_are_generator_shaped(self):
        for relative in fetch_assets.BUNDLES:
            path = fetch_assets.REPO_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            rules = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
            self.assertTrue(rules, relative)
            self.assertEqual(rules, sorted(set(rules)), relative)


if __name__ == "__main__":
    unittest.main()

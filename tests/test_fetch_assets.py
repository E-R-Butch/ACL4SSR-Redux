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

    def test_registrable_domain(self):
        self.assertEqual(fetch_assets.registrable_domain("a.b.example.co.uk"), "example.co.uk")
        self.assertEqual(fetch_assets.registrable_domain("ads.example.com"), "example.com")
        self.assertEqual(fetch_assets.registrable_domain("example.com"), "example.com")
        self.assertEqual(fetch_assets.registrable_domain("shop.example.com.cn"), "example.com.cn")

    def test_tranco_reading_keeps_registrable_domains_within_the_limit(self):
        import io
        import zipfile

        csv = "1,example.com\r\n2,ads.example.com\r\n3,beyond.example\r\n"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("top-1m.csv", csv)

        popular = fetch_assets.read_tranco_registrable(buffer.getvalue(), limit=2)

        self.assertEqual(popular, {"example.com"})

    def test_value_covered_by_parent_suffix(self):
        self.assertTrue(fetch_assets.is_value_covered("ads.example.com", {"example.com"}))
        self.assertFalse(fetch_assets.is_value_covered("notexample.com", {"example.com"}))

    def test_anti_ad_keeps_only_uncovered_unpopular_domains(self):
        content = "# comment\nnewads.example\ncovered.example\npopular.example\nads.popular.example\n"
        popular = {"popular.example"}
        decided = {"covered.example"}

        output = fetch_assets.process_anti_ad(content, popular, decided)

        self.assertIn("DOMAIN-SUFFIX,newads.example", output)
        self.assertNotIn("covered.example", output)
        self.assertNotIn("popular.example", output)
        self.assertIn("# 数量：1条", output)

    def test_increment_and_merged_output_are_not_their_own_coverage(self):
        # Upstream lists can gain an increment domain during a sync. Test the
        # excluded files, not disjointness between changing repository lists.
        increment = "Rules/Ruleset/Active/AdBlock/BanAntiAD.list"
        merged = "Rules/Outputs/MergedADBan.list"
        fixtures = {
            increment: {"increment.example", "shared.example"},
            merged: {"increment.example", "merged.example", "shared.example"},
            "Rules/Ruleset/Active/AdBlock/BanEasyListChina.list": {"elsewhere.example", "shared.example"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            # Rebase the real configuration so removing either exclusion still
            # breaks this regression test.
            excluded = tuple(
                root / path.relative_to(fetch_assets.REPO_ROOT)
                for path in fetch_assets.COVERAGE_EXCLUDE_PATHS
            )
            for relative, values in fixtures.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "".join(f"DOMAIN-SUFFIX,{value}\n" for value in sorted(values)), encoding="utf-8"
                )

            with mock.patch.object(fetch_assets, "REPO_ROOT", root):
                self.assertEqual(
                    fetch_assets.repo_rule_values(),
                    {"increment.example", "merged.example", "elsewhere.example", "shared.example"},
                )
                coverage = fetch_assets.repo_rule_values(excluded)
                self.assertEqual(coverage, {"elsewhere.example", "shared.example"})

                content = "increment.example\nmerged.example\nshared.example\n"
                first = fetch_assets.process_anti_ad(content, set(), coverage)
                self.assertIn("DOMAIN-SUFFIX,increment.example", first)
                self.assertIn("DOMAIN-SUFFIX,merged.example", first)
                self.assertNotIn("DOMAIN-SUFFIX,shared.example", first)
                for relative in (increment, merged):
                    (root / relative).write_text(first, encoding="utf-8")
                second = fetch_assets.process_anti_ad(content, set(), fetch_assets.repo_rule_values(excluded))
                self.assertEqual(first, second, "the increment must survive a repeated sync")

    def test_build_outputs_uses_configured_anti_ad_coverage(self):
        fetched = {key: "" for key in fetch_assets.TARGETS}
        fetched["ANTI_AD_DOMAINS"] = "covered.example\npopular.example\nnew.example\n"
        with (
            mock.patch.object(fetch_assets, "repo_rule_values", return_value={"covered.example"}) as coverage,
            mock.patch.object(fetch_assets, "process_gfwlist", return_value=""),
            mock.patch.object(fetch_assets, "BUNDLES", {}),
        ):
            outputs = fetch_assets.build_outputs(fetched, {"popular.example"})

        coverage.assert_called_once_with(fetch_assets.COVERAGE_EXCLUDE_PATHS)
        rules = [
            line for line in outputs[fetch_assets.ANTI_AD_TARGET].splitlines()
            if line and not line.startswith("#")
        ]
        self.assertEqual(rules, ["DOMAIN-SUFFIX,new.example"])


if __name__ == "__main__":
    unittest.main()

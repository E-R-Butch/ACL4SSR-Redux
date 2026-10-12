import unittest

from scripts import split_providers


def make(line, family="privacy"):
    rule = split_providers.parse_rule(line, "test")
    rule["family"] = family
    return rule


class ParseRuleTests(unittest.TestCase):
    def test_parses_supported_rule(self):
        rule = make("DOMAIN-SUFFIX,Example.COM")

        self.assertEqual(rule["type"], "DOMAIN-SUFFIX")
        self.assertEqual(rule["value"], "example.com")
        self.assertFalse(rule["no_resolve"])

    def test_detects_no_resolve(self):
        self.assertTrue(make("IP-CIDR,203.0.113.0/24,no-resolve")["no_resolve"])

    def test_rejects_unsupported_rule(self):
        with self.assertRaises(ValueError):
            make("SRC-IP-CIDR,203.0.113.0/24")

    def test_rejects_malformed_rule(self):
        with self.assertRaises(ValueError):
            make("DOMAIN-SUFFIX")


class DedupeTests(unittest.TestCase):
    def test_exact_duplicate_is_dropped(self):
        kept, reasons = split_providers.dedupe([make("DOMAIN,a.example"), make("DOMAIN,a.example")])

        self.assertEqual([rule["value"] for rule in kept], ["a.example"])
        self.assertEqual(reasons["exact"], 1)

    def test_later_domain_covered_by_earlier_suffix_is_dropped(self):
        kept, reasons = split_providers.dedupe(
            [make("DOMAIN-SUFFIX,example.com"), make("DOMAIN,ads.example.com")]
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(reasons["suffix"], 1)

    def test_later_suffix_covered_by_earlier_parent_suffix_is_dropped(self):
        kept, reasons = split_providers.dedupe(
            [make("DOMAIN-SUFFIX,example.com"), make("DOMAIN-SUFFIX,ads.example.com")]
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(reasons["suffix"], 1)

    def test_keyword_coverage_is_dropped(self):
        kept, reasons = split_providers.dedupe(
            [make("DOMAIN-KEYWORD,tracking"), make("DOMAIN-SUFFIX,tracking.example.com")]
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(reasons["keyword"], 1)

    def test_unrelated_suffix_is_kept(self):
        kept, reasons = split_providers.dedupe(
            [make("DOMAIN-SUFFIX,example.com"), make("DOMAIN-SUFFIX,notexample.com")]
        )

        self.assertEqual(len(kept), 2)
        self.assertEqual(sum(reasons.values()), 0)

    def test_contained_network_with_same_flag_is_dropped(self):
        kept, reasons = split_providers.dedupe(
            [
                make("IP-CIDR,203.0.113.0/24,no-resolve"),
                make("IP-CIDR,203.0.113.128/25,no-resolve", family="adblock"),
            ]
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(reasons["cidr"], 1)

    def test_contained_network_with_other_flag_is_kept(self):
        kept, reasons = split_providers.dedupe(
            [
                make("IP-CIDR,203.0.113.0/24,no-resolve"),
                make("IP-CIDR,203.0.113.128/25", family="adblock"),
            ]
        )

        self.assertEqual(len(kept), 2)
        self.assertEqual(sum(reasons.values()), 0)

    def test_coverage_does_not_cross_rule_families_of_type(self):
        kept, _ = split_providers.dedupe([make("DOMAIN,a.example"), make("DOMAIN-SUFFIX,a.example")])

        self.assertEqual(len(kept), 2)


class PartitionTests(unittest.TestCase):
    def test_chunks_respect_the_limit_and_stay_balanced(self):
        entries = [make(f"DOMAIN-SUFFIX,host{index}.example") for index in range(1000)]

        chunks = split_providers.partition(entries, 300)

        self.assertEqual(len(chunks), 4)
        self.assertLessEqual(max(len(chunk) for chunk in chunks), 300)
        self.assertGreater(min(len(chunk) for chunk in chunks), 220)
        self.assertEqual(sum(len(chunk) for chunk in chunks), 1000)

    def test_partition_is_deterministic(self):
        entries = [make(f"DOMAIN-SUFFIX,host{index}.example") for index in range(500)]

        first = [rule["line"] for chunk in split_providers.partition(entries, 120) for rule in chunk]
        second = [rule["line"] for chunk in split_providers.partition(entries, 120) for rule in chunk]

        self.assertEqual(first, second)

    def test_empty_input_yields_no_chunks(self):
        self.assertEqual(split_providers.partition([], 100), [])


class ProviderRenderTests(unittest.TestCase):
    def test_render_and_parse_round_trip(self):
        text = split_providers.render_provider([make('DOMAIN-KEYWORD,foo\\"bar"')])

        self.assertEqual(split_providers.parse_provider(text), ['DOMAIN-KEYWORD,foo\\"bar"'])


class CommittedProviderTests(unittest.TestCase):
    def test_generated_set_is_unique_capped_and_balanced(self):
        files, _, total, kept = split_providers.build(max_rules=split_providers.DEFAULT_MAX_RULES)

        split_providers.verify(files, kept, split_providers.DEFAULT_MAX_RULES)

        self.assertLess(kept, total)
        sizes = [entry["rules"] for entry in files]
        self.assertGreaterEqual(min(sizes), split_providers.DEFAULT_MAX_RULES * 0.85)
        self.assertLessEqual(max(sizes), split_providers.DEFAULT_MAX_RULES)

    def test_every_file_maps_to_its_family_group(self):
        files, reasons, total, kept = split_providers.build()

        for entry in files:
            self.assertEqual(entry["group"], split_providers.FAMILIES[entry["family"]]["group"])
            self.assertEqual(entry["action"], split_providers.FAMILIES[entry["family"]]["action"])

        manifest = split_providers.manifest(files, reasons, total, kept, split_providers.DEFAULT_MAX_RULES)
        self.assertEqual(len(manifest["ruleset_lines"]), len(files))
        self.assertIn("RULE-SET,acl4ssr-adprivacy-adblock-01,🛑 广告拦截", manifest["ruleset_lines"])

    def test_manifest_counts_match_the_files(self):
        files, reasons, total, kept = split_providers.build()
        manifest = split_providers.manifest(files, reasons, total, kept, split_providers.DEFAULT_MAX_RULES)

        self.assertEqual(manifest["rules"]["parsed"], total)
        self.assertEqual(manifest["rules"]["kept"], kept)
        self.assertEqual(manifest["rules"]["dropped"], total - kept)
        self.assertEqual(sum(entry["rules"] for entry in manifest["files"]), kept)


if __name__ == "__main__":
    unittest.main()

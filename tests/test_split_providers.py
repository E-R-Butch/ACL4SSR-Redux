import ipaddress
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import yaml

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

    def test_identical_network_with_other_flag_is_kept(self):
        for token, value in (("IP-CIDR", "203.0.113.0/24"), ("IP-CIDR6", "2001:db8::/32")):
            for first, second in (("", ",no-resolve"), (",no-resolve", "")):
                with self.subTest(token=token, first=first):
                    kept, reasons = split_providers.dedupe([
                        make(f"{token},{value}{first}"),
                        make(f"{token},{value}{second}", family="adblock"),
                    ])
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

    def test_nonpositive_capacity_is_rejected(self):
        for max_rules in (0, -1):
            with self.subTest(max_rules=max_rules), self.assertRaises(ValueError):
                split_providers.partition([make("DOMAIN,a.example")], max_rules)

    def test_empty_input_yields_no_chunks(self):
        self.assertEqual(split_providers.partition([], 100), [])


class ProviderRenderTests(unittest.TestCase):
    def test_render_and_parse_round_trip(self):
        text = split_providers.render_provider([make('DOMAIN-KEYWORD,foo\\"bar"')])

        self.assertEqual(split_providers.parse_provider(text), ['DOMAIN-KEYWORD,foo\\"bar"'])


def first_family(entries, host, address, port):
    """Small independent matcher for the domain, IP and port fixture subset."""
    for entry in entries:
        token, value, *options = entry["line"].split(",")
        match = False
        if token == "DOMAIN":
            match = host == value
        elif token == "DOMAIN-SUFFIX":
            match = host == value or host.endswith("." + value)
        elif token == "DOMAIN-KEYWORD":
            match = value in host
        elif token in {"IP-CIDR", "IP-CIDR6"}:
            match = address is not None and ipaddress.ip_address(address) in ipaddress.ip_network(value)
        elif token == "DST-PORT":
            match = port == int(value)
        if match:
            return entry["family"]
    return None


def emitted_entries(files):
    return [
        {"line": line, "family": entry["family"]}
        for entry in files
        for line in yaml.safe_load(entry["text"])["payload"]
    ]


class PrecedenceTests(unittest.TestCase):
    def test_split_preserves_first_match_across_family_boundaries(self):
        sources = (
            ("privacy", "early.list", [
                "DOMAIN-SUFFIX,tracker.example", "DST-PORT,443",
                "IP-CIDR,203.0.113.0/25,no-resolve",
                "IP-CIDR6,2001:db8::/48,no-resolve",
            ]),
            ("adblock", "middle.list", [
                "DOMAIN-KEYWORD,tracker", "DOMAIN,exact.later.example",
                "DOMAIN,port.example", "DST-PORT,80",
                "IP-CIDR,203.0.113.0/24,no-resolve",
                "IP-CIDR6,2001:db8::/32,no-resolve",
            ]),
            ("privacy", "late.list", [
                "DOMAIN-SUFFIX,later.example", "DOMAIN,late.example",
            ]),
        )
        original = [make(line, family) for family, _, lines in sources for line in lines]
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for _, name, lines in sources:
                (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            with mock.patch.object(split_providers, "REPO_ROOT", root), mock.patch.object(
                split_providers, "SOURCES", tuple((family, name) for family, name, _ in sources)
            ):
                files, reasons, total, kept = split_providers.build(max_rules=2)
        split_providers.verify(files, kept, 2)
        generated = emitted_entries(files)
        for host in ("tracker.example", "sub.tracker.example", "othertracker.example", "exact.later.example",
                     "sub.later.example", "port.example", "late.example", "unmatched.example"):
            for address in (None, "203.0.113.1", "203.0.113.200", "2001:db8::1", "2001:db8:1::1"):
                for port in (53, 80, 443):
                    with self.subTest(host=host, address=address, port=port):
                        self.assertEqual(first_family(generated, host, address, port),
                                         first_family(original, host, address, port))
        data = split_providers.manifest(files, reasons, total, kept, 2)
        self.assertEqual(data["ruleset_lines"], [
            f"RULE-SET,{entry['file'][:-5]},{entry['group']}" for entry in files
        ])
        self.assertEqual(len({entry["file"] for entry in files}), len(files))

    def test_empty_or_fully_deduplicated_stage_keeps_unique_names_and_order(self):
        for early, middle, expected_stages in (
            ("", "DOMAIN,middle.example", [2, 3]),
            ("DOMAIN,shared.example", "DOMAIN,shared.example", [1, 3]),
        ):
            with self.subTest(expected_stages=expected_stages), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                for name, content in (("early.list", early), ("middle.list", middle),
                                      ("late.list", "DOMAIN,late.example")):
                    (root / name).write_text(content + "\n", encoding="utf-8")
                sources = (("privacy", "early.list"), ("adblock", "middle.list"), ("privacy", "late.list"))
                with mock.patch.object(split_providers, "REPO_ROOT", root), mock.patch.object(split_providers, "SOURCES", sources):
                    files, _, _, kept = split_providers.build(max_rules=2)
                split_providers.verify(files, kept, 2)
                self.assertEqual([entry["stage"] for entry in files], expected_stages)
                self.assertEqual(len({entry["file"] for entry in files}), len(files))
                for entry in files:
                    self.assertTrue({"file", "family", "group", "action", "rules", "sha256", "text"} <= entry.keys())

    def test_committed_omniture_retains_privacy_action(self):
        original = [rule for family, relative in split_providers.SOURCES
                    for rule in split_providers.read_source(split_providers.REPO_ROOT / relative, family)]
        files, _, _, _ = split_providers.build()
        self.assertEqual(first_family(original, "omniture.com", None, 53), "privacy")
        self.assertEqual(first_family(emitted_entries(files), "omniture.com", None, 53), "privacy")


class ManifestCheckTests(unittest.TestCase):
    def test_check_requires_current_manifest_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sources = (("privacy", "early.list"), ("adblock", "late.list"))
            (root / "early.list").write_text("DOMAIN,early.example\n", encoding="utf-8")
            (root / "late.list").write_text("DOMAIN,late.example\n", encoding="utf-8")
            out = root / "providers"
            with mock.patch.object(split_providers, "REPO_ROOT", root), mock.patch.object(split_providers, "SOURCES", sources):
                _, expected = split_providers.run(out, 2, check=False)
                manifest_path = out / "providers.manifest.json"
                self.assertEqual(split_providers.run(out, 2, check=True)[0], 0)
                changed = dict(expected, ruleset_lines=list(reversed(expected["ruleset_lines"])))
                for content in (json.dumps(changed), "not json"):
                    with self.subTest(content=content):
                        manifest_path.write_text(content, encoding="utf-8")
                        self.assertGreater(split_providers.run(out, 2, check=True)[0], 0)
                        self.assertEqual(manifest_path.read_text(encoding="utf-8"), content)
                manifest_path.unlink()
                self.assertGreater(split_providers.run(out, 2, check=True)[0], 0)
                self.assertFalse(manifest_path.exists())

    def test_check_detects_payload_hash_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "source.list").write_text("DOMAIN,early.example\n", encoding="utf-8")
            out = root / "providers"
            with mock.patch.object(split_providers, "REPO_ROOT", root), mock.patch.object(
                split_providers, "SOURCES", (("privacy", "source.list"),)
            ):
                _, data = split_providers.run(out, 2, check=False)
                target = out / data["files"][0]["file"]
                target.write_text(target.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
                self.assertGreater(split_providers.run(out, 2, check=True)[0], 0)


class CommittedProviderTests(unittest.TestCase):
    def test_generated_set_is_unique_capped_and_balanced(self):
        files, _, total, kept = split_providers.build(max_rules=split_providers.DEFAULT_MAX_RULES)

        split_providers.verify(files, kept, split_providers.DEFAULT_MAX_RULES)

        self.assertLess(kept, total)
        sizes = [entry["rules"] for entry in files]
        # Small precedence-boundary stages cannot be merged across an action.
        # Every larger stage must still satisfy the original density guard.
        for stage in {entry["stage"] for entry in files}:
            stage_sizes = [entry["rules"] for entry in files if entry["stage"] == stage]
            if sum(stage_sizes) < split_providers.DEFAULT_MAX_RULES:
                self.assertEqual(len(stage_sizes), 1)
            else:
                self.assertGreaterEqual(min(stage_sizes), split_providers.DEFAULT_MAX_RULES * 0.85)
        self.assertEqual([(entry["stage"], entry["family"]) for entry in files if entry["stage"] == 1],
                         [(1, "privacy")])
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

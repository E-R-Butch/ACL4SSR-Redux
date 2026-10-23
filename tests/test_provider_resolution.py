"""Regression coverage for Mihomo's shared, one-attempt DNS match state."""

import copy
import ipaddress
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import split_providers


def make(line, family="privacy"):
    rule = split_providers.parse_rule(line, "fixture")
    return dict(rule, family=family)


def evaluate(entries, answer, address=None, host="query.example"):
    """Independent fixture matcher: resolving rules mutate shared metadata.

    Models common/ipcidr.go, common/geoip.go and tunnel/tunnel.go: the first
    resolving IP rule attempts DNS once, including failed answers, and later
    no-resolve rules can use the resulting address. Classical providers do not
    retry earlier rules after that mutation.
    """
    attempted = False
    for entry in entries:
        token, value, *flags = entry["line"].split(",")
        matched = False
        if token in {"IP-CIDR", "IP-CIDR6", "GEOIP"}:
            if "no-resolve" not in flags and not attempted and address is None:
                address = answer
                attempted = True
            if address is not None:
                ip = ipaddress.ip_address(address)
                if token == "GEOIP":
                    assert value == "lan"
                    matched = any(ip in ipaddress.ip_network(net) for net in (
                        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"
                    ))
                else:
                    matched = ip in ipaddress.ip_network(value)
        elif token == "DOMAIN":
            matched = host == value
        if matched:
            return entry["family"], attempted, address
    return None, attempted, address


def build_fixture(sources, capacity):
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for _, name, lines in sources:
            (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        with mock.patch.object(split_providers, "REPO_ROOT", root), mock.patch.object(
            split_providers, "SOURCES", tuple((family, name) for family, name, _ in sources)
        ):
            files, reasons, total, kept = split_providers.build(max_rules=capacity)
        split_providers.verify(files, kept, capacity)
    generated = [make(line, entry["family"]) for entry in files
                 for line in split_providers.parse_provider(entry["text"])]
    return generated, files, reasons, total, kept


class ResolutionOrderTests(unittest.TestCase):
    def test_resolving_stages_keep_order_across_chunks_and_families(self):
        cases = (
            ("IP-CIDR,203.0.1.0/24", "IP-CIDR,11.0.1.0/24,no-resolve", "11.0.1.1"),
            ("IP-CIDR6,2001:db8:1::/48", "IP-CIDR6,2001:db8:2::/48,no-resolve", "2001:db8:2::1"),
            ("GEOIP,lan", "IP-CIDR,11.0.1.0/24,no-resolve", "11.0.1.1"),
            ("IP-CIDR,203.0.1.0/24", "GEOIP,lan,no-resolve", "10.1.2.3"),
        )
        for resolver, passive, answer in cases:
            for lines in ([resolver, passive], [passive, resolver],
                          [resolver, "DOMAIN,query.example", passive],
                          ["DOMAIN,query.example", resolver, passive]):
                for capacity in (1, 2, 3, 100):
                    with self.subTest(lines=lines, capacity=capacity):
                        sources = (
                            ("privacy", "early.list", lines),
                            ("adblock", "middle.list", ["DOMAIN,query.example"]),
                            ("privacy", "late.list", ["DOMAIN,other.example"]),
                        )
                        original = [make(line, family) for family, _, values in sources for line in values]
                        generated, files, _, _, _ = build_fixture(sources, capacity)
                        for dns_answer in (answer, None):
                            for address in (None, answer):
                                for host in ("query.example", "unmatched.example"):
                                    self.assertEqual(evaluate(generated, dns_answer, address, host),
                                                     evaluate(original, dns_answer, address, host))
                        self.assertTrue(all(entry["rules"] <= capacity for entry in files))

    def test_dns_sensitive_partition_is_contiguous_balanced_and_capped(self):
        entries = [make("IP-CIDR,203.0.1.0/24")]
        entries += [make(f"DOMAIN,host{index}.example") for index in range(999)]
        chunks = split_providers.partition(entries, 300)
        self.assertEqual([rule for chunk in chunks for rule in chunk], entries)
        self.assertEqual([len(chunk) for chunk in chunks], [250] * 4)


class ResolutionDedupeTests(unittest.TestCase):
    def test_no_resolve_coverage_cannot_cross_the_first_dns_attempt(self):
        for passive, later, answer in (
            ("IP-CIDR,11.0.0.0/16,no-resolve", "IP-CIDR,11.0.0.0/16,no-resolve", "11.0.1.1"),
            ("IP-CIDR,11.0.0.0/16,no-resolve", "IP-CIDR,11.0.1.0/24,no-resolve", "11.0.1.1"),
            ("IP-CIDR6,2001:db8::/32,no-resolve", "IP-CIDR6,2001:db8::/32,no-resolve", "2001:db8::1"),
            ("IP-CIDR6,2001:db8::/32,no-resolve", "IP-CIDR6,2001:db8:2::/48,no-resolve", "2001:db8:2::1"),
            ("GEOIP,lan,no-resolve", "GEOIP,lan,no-resolve", "10.1.2.3"),
        ):
            for resolver in ("IP-CIDR,203.0.1.0/24", "IP-CIDR6,2001:db8:ffff::/48"):
                for one_stage in (True, False):
                    with self.subTest(passive=passive, later=later, resolver=resolver, one_stage=one_stage):
                        sources = (
                            ("privacy", "early.list", [passive]),
                            ("privacy" if one_stage else "adblock", "middle.list", [resolver]),
                            ("privacy", "late.list", [later, later, "DOMAIN,query.example"]),
                        )
                        original = [make(line, family) for family, _, values in sources for line in values]
                        generated, _, reasons, total, kept = build_fixture(sources, 1)
                        self.assertEqual(total - kept, 1)
                        self.assertEqual(reasons["exact"], 1)
                        for dns_answer in (answer, None):
                            for address in (None, answer):
                                self.assertEqual(evaluate(generated, dns_answer, address),
                                                 evaluate(original, dns_answer, address))

    def test_geoip_modifiers_are_distinct_and_only_one_dns_epoch_starts(self):
        entries = [make(line) for line in (
            "GEOIP,lan,no-resolve", "GEOIP,lan", "GEOIP,lan,no-resolve",
            "IP-CIDR,203.0.1.0/24", "GEOIP,lan,no-resolve",
        )]
        kept, reasons = split_providers.dedupe(entries)
        self.assertEqual([rule["line"] for rule in kept], [rule["line"] for rule in entries[:-1]])
        self.assertEqual(reasons["exact"], 1)

    def test_verify_rejects_duplicate_within_an_epoch_but_accepts_needed_repeat(self):
        sources = (("privacy", "rules.list", [
            "IP-CIDR,11.0.1.0/24,no-resolve", "IP-CIDR,203.0.1.0/24",
            "IP-CIDR,11.0.1.0/24,no-resolve", "DOMAIN,query.example",
        ]),)
        _, files, _, _, kept = build_fixture(sources, 1)
        for index in (0, 2, 3):
            with self.subTest(index=index):
                duplicated = files[:index + 1] + [copy.deepcopy(files[index])] + files[index + 1:]
                with self.assertRaises(AssertionError):
                    split_providers.verify(duplicated, kept + 1, 1)
        # Even same-file duplicates remain invalid; the exception is only for
        # no-resolve IP evaluations separated by the first resolving rule.
        for line in ("DOMAIN,query.example", "IP-CIDR,11.0.1.0/24,no-resolve"):
            duplicate_file = dict(files[0], rules=2, text=split_providers.render_provider([make(line)] * 2))
            with self.subTest(line=line), self.assertRaises(AssertionError):
                split_providers.verify([duplicate_file], 2, 2)


if __name__ == "__main__":
    unittest.main()

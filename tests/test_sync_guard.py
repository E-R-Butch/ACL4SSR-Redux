import contextlib
import io
import ipaddress
import json
import os
import pathlib
import random
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import fetch_assets, sync_guard


V4 = "Rules/Ruleset/Active/China/ChinaIp.list"
V6 = "Rules/Ruleset/Active/China/ChinaIpV6.list"
DOMAIN = "Rules/Core/ProxyGFWlist.list"
READ_HEAD_TEXT = sync_guard.read_head_text


def rules(*cidrs, version=4):
    prefix = "IP-CIDR6" if version == 6 else "IP-CIDR"
    return "# Published header\n\n" + "".join(f"{prefix},{cidr},no-resolve\n" for cidr in cidrs)


class IPGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = pathlib.Path(self.directory.name) / "repo"
        self.root.mkdir()
        self.report_path = pathlib.Path(self.directory.name) / "review.json"
        self.head = {}
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(sync_guard, "REPO_ROOT", self.root).start()
        mock.patch.object(sync_guard, "read_head_text", side_effect=self.head.get).start()
        mock.patch.dict(os.environ, {}, clear=True).start()
        self.output = io.StringIO()
        # Keep test output concise; assertions below can inspect the captured log.
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def prepare(self, baseline, candidate, path=V4):
        self.head[path] = baseline
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(candidate, encoding="utf-8")
        return target

    def review(self, path=V4):
        return sync_guard.review_ip_target(path, sync_guard.IP_TARGETS[path])

    def run_guard(self, targets):
        with mock.patch.object(sync_guard, "TARGETS", targets):
            sync_guard.main(["--ip-review-report", str(self.report_path)])

    def test_equivalent_compaction_preserves_type_modifier_header_and_addresses(self):
        baseline = rules("192.0.2.0/25", "192.0.2.128/25")
        candidate = rules("192.0.2.0/24")
        self.prepare(baseline, candidate)
        errors, replacement, report = self.review()
        self.assertEqual(errors, [])
        self.assertEqual(replacement, candidate)
        self.assertEqual(report["status"], "equivalent")
        self.assertEqual(report["retained_address_count"], "256")
        self.assertEqual(report["pending_additions"], [])
        # Even a deliberately impossible row minimum is bypassed for this
        # exact-coverage check; domain minima remain in force separately.
        self.run_guard({V4: 1000})
        self.assertEqual((self.root / V4).read_text(), candidate)

    def test_fragmentation_overlap_duplicates_and_reordering_are_equivalent(self):
        baseline = rules("192.0.2.0/24")
        candidate = rules("192.0.2.128/25", "192.0.2.0/25", "192.0.2.64/26", "192.0.2.0/25")
        self.prepare(baseline, candidate)
        errors, replacement, report = self.review()
        self.assertEqual(errors, [])
        self.assertEqual(replacement, baseline)
        self.assertEqual(report["status"], "equivalent")

    def test_strict_superset_retains_baseline_and_reports_only_new_addresses(self):
        baseline = rules("192.0.2.0/25")
        self.prepare(baseline, rules("192.0.2.0/24", "198.51.100.0/24"))
        errors, replacement, report = self.review()
        self.assertEqual(errors, [])
        self.assertEqual(replacement, baseline)
        self.assertEqual(report["status"], "held_for_review")
        self.assertEqual(report["pending_additions"], ["192.0.2.128/25", "198.51.100.0/24"])
        self.assertEqual(report["added_address_count"], "384")

    def test_one_address_removal_is_held_even_with_bigger_total_and_equal_rule_count(self):
        self.prepare(rules("192.0.2.0/24", "203.0.113.7/32"), rules("192.0.2.0/24", "198.51.100.0/24"))
        errors, replacement, report = self.review()
        self.assertEqual(errors, [])
        self.assertEqual(replacement, rules("192.0.2.0/24", "203.0.113.7/32"))
        self.assertEqual(report["status"], "held_for_review")
        self.assertEqual(report["pending_removals"], ["203.0.113.7/32"])
        self.assertEqual(report["missing_coverage"], ["203.0.113.7/32"])
        self.assertEqual(report["missing_address_count"], "1")
        self.assertEqual(report["pending_additions"], ["198.51.100.0/24"])

    def test_equal_size_replacement_and_subset_retain_complete_baseline(self):
        for candidate in (rules("198.51.100.0/24"), rules("192.0.2.0/25")):
            with self.subTest(candidate=candidate):
                target = self.prepare(rules("192.0.2.0/24"), candidate)
                errors, replacement, report = self.review()
                self.assertEqual(errors, [])
                self.assertEqual(replacement, rules("192.0.2.0/24"))
                self.assertEqual(report["status"], "held_for_review")
                self.assertTrue(report["pending_removals"])
                self.run_guard({V4: 1000})
                self.assertEqual(target.read_text(), rules("192.0.2.0/24"))

    def test_nov20_ipv6_removal_and_addition_keep_published_coverage_and_domain_sync(self):
        baseline = rules("2402:9e80::/48", "2406:bdc0::/32", version=6)
        candidate = rules("2402:9e80::/48", "2402:9e80:7::/48", version=6)
        target = self.prepare(baseline, candidate, V6)
        self.prepare(rules("192.0.2.0/24"), rules("192.0.2.0/23"))
        domain_candidate = "DOMAIN-SUFFIX,a.example\nDOMAIN-SUFFIX,b.example\n"
        domain = self.prepare("DOMAIN-SUFFIX,a.example\n", domain_candidate, DOMAIN)
        summary = self.root / "summary.md"
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            self.run_guard({V4: 1000, V6: 100, DOMAIN: 1})
        self.assertEqual(target.read_text(), baseline)
        self.assertEqual((self.root / V4).read_text(), rules("192.0.2.0/24"))
        self.assertEqual(domain.read_text(), domain_candidate)
        report = json.loads(self.report_path.read_text())
        self.assertEqual(report["errors"], [])
        v6 = next(item for item in report["ip_reviews"] if item["ip_version"] == 6)
        self.assertEqual(v6["pending_removals"], ["2406:bdc0::/32"])
        self.assertEqual(v6["pending_additions"], ["2402:9e80:7::/48"])
        self.assertEqual(v6["missing_address_count"], str(2**96))
        self.assertEqual(v6["retained_address_count"], str(2**96 + 2**80))
        self.assertIn("2406:bdc0::/32", summary.read_text())
        self.assertIn("removed addresses remain published", summary.read_text())
        # A second sync still holds the same upstream changes for review.
        self.head[V6] = target.read_text()
        target.write_text(candidate)
        self.run_guard({V4: 1000, V6: 100, DOMAIN: 1})
        self.assertEqual(target.read_text(), baseline)

    def test_removal_retains_published_text_byte_for_byte(self):
        baseline = ("# Keep this exact header\n\n"
                    "IP-CIDR6,2001:db8::/33,no-resolve\n"
                    "IP-CIDR6,2001:db8:8000::/33,no-resolve\n"
                    "# Preserve trailing comment and missing final newline")
        target = self.prepare(baseline, rules("2001:db8::/33", version=6), V6)
        self.run_guard({V6: 100})
        self.assertEqual(target.read_bytes(), baseline.encode("utf-8"))
        report = json.loads(self.report_path.read_text())["ip_reviews"][0]
        self.assertEqual(report["retained_rule_count"], 2)
        self.assertEqual(report["output_policy"], "retain_published_file")

    def commit_raw_baseline(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init", "-q")
        git("-c", "core.autocrlf=false", "add", "--", path)
        git("-c", "user.name=IP Guard Tests", "-c", "user.email=ip-guard@example.invalid",
            "commit", "-qm", "test baseline")
        return target

    def test_git_blob_crlf_and_missing_final_newline_are_retained_exactly(self):
        baseline = (b"# Published CRLF header\r\n\r\n"
                    b"IP-CIDR6,2001:db8::/32,no-resolve\r\n"
                    b"IP-CIDR6,2406:bdc0::/32,no-resolve")
        target = self.commit_raw_baseline(V6, baseline)
        target.write_text(rules("2001:db8::/32", version=6))
        with mock.patch.object(sync_guard, "read_head_text", READ_HEAD_TEXT):
            self.run_guard({V6: 100})
        self.assertEqual(target.read_bytes(), baseline)

    def test_invalid_utf8_git_baseline_remains_fatal(self):
        target = self.commit_raw_baseline(V6, b"# invalid UTF-8: \xff\n")
        candidate = rules("2001:db8::/32", version=6)
        target.write_text(candidate)
        with mock.patch.object(sync_guard, "read_head_text", READ_HEAD_TEXT), self.assertRaises(SystemExit):
            self.run_guard({V6: 100})
        self.assertEqual(target.read_text(), candidate)
        self.assertTrue(json.loads(self.report_path.read_text())["errors"])

    def test_removal_fallback_cannot_mask_other_invalid_inputs(self):
        baseline = rules("2001:db8::/32", "2406:bdc0::/32", version=6)
        candidate = rules("2001:db8::/32", version=6)
        target = self.prepare(baseline, candidate, V6)
        self.prepare(rules("192.0.2.0/24"), "<html>upstream unavailable</html>\n")
        with self.assertRaises(SystemExit):
            self.run_guard({V4: 1000, V6: 100})
        self.assertEqual(target.read_text(), candidate)

    def test_invalid_cidr_rule_type_family_options_and_error_page_fail(self):
        cases = [
            "IP-CIDR,192.0.2.1/24,no-resolve\n",
            "IP-CIDR,192.0.2.0/33,no-resolve\n",
            "IP-CIDR,192.0.2.0,no-resolve\n",
            "IP-CIDR,192.0.2.0/255.255.255.0,no-resolve\n",
            "IP-CIDR,::/0,no-resolve\n",
            "IP-CIDR6,192.0.2.0/24,no-resolve\n",
            "DOMAIN,example.com\n",
            "IP-CIDR,192.0.2.0/24\n",
            "IP-CIDR,192.0.2.0/24,DIRECT\n",
            "IP-CIDR,192.0.2.0/24,no-resolve,extra\n",
            "<html>502 Bad Gateway</html>\n",
            "# upstream rate limit\n" + rules("192.0.2.0/24"),
            "", "# empty\n",
        ]
        for candidate in cases:
            with self.subTest(candidate=candidate):
                self.prepare(rules("192.0.2.0/24"), candidate)
                errors, replacement, _ = self.review()
                self.assertTrue(errors)
                self.assertIsNone(replacement)

    def test_scoped_ipv6_is_rejected_in_candidate_and_published_baseline(self):
        valid = rules("2001:db8::/64", version=6)
        scoped = rules("2001:db8::%eth0/64", version=6)
        for baseline, candidate in ((valid, scoped), (scoped, valid)):
            with self.subTest(baseline=baseline):
                self.prepare(baseline, candidate, V6)
                self.assertTrue(self.review(V6)[0])

    def test_review_report_cannot_overwrite_active_rule_file(self):
        candidate = rules("192.0.2.0/24")
        target = self.prepare(rules("192.0.2.0/25"), candidate)
        with mock.patch.object(sync_guard, "TARGETS", {V4: 1000}), self.assertRaises(SystemExit):
            sync_guard.main(["--ip-review-report", str(target)])
        self.assertEqual(target.read_text(), candidate)

    def test_missing_empty_or_invalid_baseline_fails_closed(self):
        for baseline in (None, "", rules("192.0.2.1/24")):
            with self.subTest(baseline=baseline):
                self.prepare(baseline, rules("192.0.2.0/24"))
                errors, replacement, _ = self.review()
                self.assertTrue(errors)
                self.assertIsNone(replacement)

    def test_missing_directory_symlink_and_invalid_encoding_fail(self):
        self.assertTrue(self.review()[0])
        target = self.prepare(rules("192.0.2.0/24"), rules("192.0.2.0/24"))
        target.write_bytes(b"\xff")
        self.assertTrue(self.review()[0])
        target.unlink()
        target.mkdir()
        self.assertTrue(self.review()[0])
        target.rmdir()
        other = self.root / "other.list"
        other.write_text(rules("192.0.2.0/24"))
        target.symlink_to(other)
        self.assertTrue(self.review()[0])

    def test_ipv6_compaction_superset_missing_and_exact_large_counts(self):
        baseline = rules("2001:db8::/33", "2001:db8:8000::/33", version=6)
        candidate = rules("2001:db8::/31", version=6)
        self.prepare(baseline, candidate, V6)
        errors, replacement, report = self.review(V6)
        self.assertEqual(errors, [])
        self.assertEqual(replacement, rules("2001:db8::/32", version=6))
        self.assertEqual(report["pending_additions"], ["2001:db9::/32"])
        self.assertEqual(report["retained_address_count"], str(2**96))
        self.prepare(baseline, rules("2001:db8::/33", version=6), V6)
        errors, replacement, report = self.review(V6)
        self.assertEqual(errors, [])
        self.assertEqual(replacement, baseline)
        self.assertEqual(report["output_policy"], "retain_published_file")
        self.assertEqual(report["retained_rule_count"], 2)
        self.assertEqual(report["pending_removals"], ["2001:db8:8000::/33"])

    def test_report_and_summary_include_all_additions_while_log_is_bounded(self):
        candidate = rules("192.0.2.0/32", *[f"198.51.100.{i}/32" for i in range(0, 80, 2)])
        target = self.prepare(rules("192.0.2.0/32"), candidate)
        summary = self.root / "summary.md"
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            self.run_guard({V4: 1000})
        report = json.loads(self.report_path.read_text())["ip_reviews"][0]
        self.assertEqual(len(report["pending_additions"]), 40)
        self.assertIn("198.51.100.78/32", summary.read_text())
        self.assertNotIn("198.51.100.78/32", self.output.getvalue())
        self.assertEqual(target.read_text(), rules("192.0.2.0/32"))

    def test_bad_domain_guard_leaves_every_ip_file_untouched(self):
        candidate = rules("192.0.2.0/24")
        target = self.prepare(rules("192.0.2.0/25"), candidate)
        self.prepare("DOMAIN-SUFFIX,a.example\n", "<html>bad gateway</html>\n", DOMAIN)
        with self.assertRaises(SystemExit):
            self.run_guard({V4: 1000, DOMAIN: 1})
        self.assertEqual(target.read_text(), candidate)

    def test_bad_ipv6_leaves_valid_ipv4_untouched(self):
        candidate = rules("192.0.2.0/24")
        target = self.prepare(rules("192.0.2.0/25"), candidate)
        self.prepare(rules("2001:db8::/32", version=6), "IP-CIDR6,2001:db8::1/32,no-resolve\n", V6)
        with self.assertRaises(SystemExit):
            self.run_guard({V4: 1000, V6: 100})
        self.assertEqual(target.read_text(), candidate)

    def test_report_publication_failure_leaves_ip_files_untouched(self):
        candidate = rules("192.0.2.0/24")
        target = self.prepare(rules("192.0.2.0/25"), candidate)
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.root / "summary")}), \
                mock.patch.object(sync_guard, "MAX_REVIEW_SUMMARY_BYTES", 1), self.assertRaises(SystemExit):
            self.run_guard({V4: 1000})
        self.assertEqual(target.read_text(), candidate)

    def test_safe_domain_updates_continue_and_ip_compaction_is_idempotent(self):
        baseline = rules("192.0.2.0/25", "192.0.2.128/25")
        target = self.prepare(baseline, rules("192.0.2.0/23"))
        domain_candidate = "DOMAIN-SUFFIX,a.example\nDOMAIN-SUFFIX,b.example\n"
        domain = self.prepare("DOMAIN-SUFFIX,a.example\n", domain_candidate, DOMAIN)
        self.run_guard({V4: 1000, DOMAIN: 1})
        compacted = target.read_text()
        self.assertEqual(compacted, rules("192.0.2.0/24"))
        self.assertEqual(domain.read_text(), domain_candidate)
        self.head[V4] = compacted
        self.run_guard({V4: 1000, DOMAIN: 1})
        self.assertEqual(target.read_text(), compacted)

    def test_domain_minimum_and_drop_growth_guards_remain(self):
        baseline = "".join(f"DOMAIN-SUFFIX,{i}.example\n" for i in range(10))
        for count, minimum in ((6, 1), (21, 1), (10, 11)):
            with self.subTest(count=count, minimum=minimum):
                self.prepare(baseline, "".join(f"DOMAIN-SUFFIX,{i}.example\n" for i in range(count)), DOMAIN)
                self.assertTrue(sync_guard.validate_target(DOMAIN, minimum))


class NetworkDifferenceTests(unittest.TestCase):
    def test_boundaries_and_large_exclusion_spanning_several_networks(self):
        for version, zero, high in ((4, "0.0.0.0/0", "255.255.255.255/32"), (6, "::/0", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff/128")):
            with self.subTest(version=version):
                whole = [ipaddress.ip_network(zero)]
                last = [ipaddress.ip_network(high)]
                remainder = sync_guard.subtract_networks(whole, last)
                self.assertEqual(sum(n.num_addresses for n in remainder), whole[0].num_addresses - 1)
                self.assertEqual(sync_guard.subtract_networks(last, whole), [])
                self.assertEqual(sync_guard.subtract_networks(remainder, whole), [])

    def test_randomized_exact_set_difference_against_independent_small_address_oracle(self):
        randomizer = random.Random(7612)
        for version, root in ((4, ipaddress.ip_network("192.0.2.0/24")), (6, ipaddress.ip_network("2001:db8::/120"))):
            address_type = type(root.network_address)
            for _ in range(100):
                def sample():
                    networks = []
                    for _ in range(20):
                        bits = randomizer.randrange(9)
                        block = 2**bits
                        offset = randomizer.randrange(256 // block) * block
                        networks.append(ipaddress.ip_network(f"{address_type(int(root.network_address) + offset)}/{root.max_prefixlen - bits}"))
                    return list(ipaddress.collapse_addresses(networks))
                left, right = sample(), sample()
                actual = sync_guard.subtract_networks(left, right)
                expected = {ip for n in left for ip in n} - {ip for n in right for ip in n}
                self.assertEqual({ip for n in actual for ip in n}, expected)
                self.assertEqual(sum(n.num_addresses for n in actual), len(expected))


class RawIPFetchTests(unittest.TestCase):
    def test_raw_cidr_shapes_are_checked_before_normalization(self):
        for value in ("192.0.2.1", "192.0.2.0/255.255.255.0", "fe80::%eth0/64", "::1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fetch_assets.process_ip(value, is_v6=":" in value)

    def test_valid_ipv6_spelling_is_normalized(self):
        self.assertIn("IP-CIDR6,2001:db8::/32,no-resolve", fetch_assets.process_ip("2001:DB8:0:0::/32", is_v6=True))

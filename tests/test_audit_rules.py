import json
import tempfile
import unittest

from scripts import audit_rules


GROUP_DEFINITIONS = [
    "custom_proxy_group=🎯 全球直连`select`[]DIRECT",
    "custom_proxy_group=🛑 广告拦截`select`[]REJECT",
    "custom_proxy_group=🔒 隐私保护`select`[]REJECT-DROP",
    "custom_proxy_group=🚀 节点选择`select`[]♻️ 自动选择",
]


def build_rules(*surge_lines):
    return audit_rules.collect_ranked_rules(GROUP_DEFINITIONS + list(surge_lines))


def by_category(findings, category):
    return [finding for finding in findings if finding["category"] == category]


class GroupActionTests(unittest.TestCase):
    def test_action_classes(self):
        actions = audit_rules.parse_group_actions(GROUP_DEFINITIONS)

        self.assertEqual(actions["🎯 全球直连"], "direct")
        self.assertEqual(actions["🛑 广告拦截"], "block")
        self.assertEqual(actions["🔒 隐私保护"], "block")
        self.assertEqual(actions["🚀 节点选择"], "proxy")


class UnreachableRuleTests(unittest.TestCase):
    def test_earlier_rule_with_other_action_makes_later_rule_dead(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]DOMAIN,example.com",
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,example.com",
        )

        duplicate = by_category(audit_rules.find_unreachable(rules), "duplicate")

        self.assertEqual(len(duplicate), 1)
        self.assertEqual(duplicate[0]["victim"]["target"], "🛑 广告拦截")

    def test_same_action_overlap_is_not_reported(self):
        rules = build_rules(
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,example.com",
            "surge_ruleset=🔒 隐私保护,[]DOMAIN,example.com",
        )

        self.assertEqual(by_category(audit_rules.find_unreachable(rules), "duplicate"), [])

    def test_later_domain_covered_by_earlier_suffix(self):
        rules = build_rules(
            "surge_ruleset=🚀 节点选择,[]DOMAIN-SUFFIX,tracker.example",
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,ads.tracker.example",
        )

        shadowed = by_category(audit_rules.find_unreachable(rules), "shadowed")

        self.assertEqual(len(shadowed), 1)
        self.assertIn("ads.tracker.example", audit_rules.render_finding(shadowed[0]))

    def test_later_suffix_covered_by_earlier_parent_suffix(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]DOMAIN-SUFFIX,example.com",
            "surge_ruleset=🛑 广告拦截,[]DOMAIN-SUFFIX,ads.example.com",
        )

        self.assertEqual(len(by_category(audit_rules.find_unreachable(rules), "shadowed")), 1)

    def test_contained_network_with_matching_no_resolve_flag(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]IP-CIDR,203.0.113.0/24,no-resolve",
            "surge_ruleset=🛑 广告拦截,[]IP-CIDR,203.0.113.128/25,no-resolve",
        )

        self.assertEqual(len(by_category(audit_rules.find_unreachable(rules), "contained")), 1)

    def test_contained_network_without_matching_flag_is_not_reported(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]IP-CIDR,203.0.113.0/24,no-resolve",
            "surge_ruleset=🛑 广告拦截,[]IP-CIDR,203.0.113.128/25",
        )

        self.assertEqual(by_category(audit_rules.find_unreachable(rules), "contained"), [])

    def test_rule_order_is_taken_from_the_ini_sequence(self):
        rules = build_rules(
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,example.com",
            "surge_ruleset=🎯 全球直连,[]DOMAIN,example.com",
        )

        duplicate = by_category(audit_rules.find_unreachable(rules), "duplicate")

        self.assertEqual(len(duplicate), 1)
        self.assertEqual(duplicate[0]["victim"]["target"], "🎯 全球直连")


class BaselineTests(unittest.TestCase):
    def test_signature_ignores_line_numbers(self):
        findings = by_category(
            audit_rules.find_unreachable(
                build_rules(
                    "surge_ruleset=🎯 全球直连,[]DOMAIN-SUFFIX,example.com",
                    "surge_ruleset=🛑 广告拦截,[]DOMAIN,ads.example.com",
                )
            ),
            "shadowed",
        )
        moved = list(findings)
        moved[0] = dict(moved[0], victim=dict(moved[0]["victim"], line=moved[0]["victim"]["line"] + 500))

        self.assertEqual(audit_rules.finding_signature(findings[0]), audit_rules.finding_signature(moved[0]))

    def test_signature_changes_when_the_winner_changes(self):
        direct_winner = by_category(
            audit_rules.find_unreachable(
                build_rules(
                    "surge_ruleset=🎯 全球直连,[]DOMAIN-SUFFIX,example.com",
                    "surge_ruleset=🛑 广告拦截,[]DOMAIN,ads.example.com",
                )
            ),
            "shadowed",
        )[0]
        proxy_winner = by_category(
            audit_rules.find_unreachable(
                build_rules(
                    "surge_ruleset=🚀 节点选择,[]DOMAIN-SUFFIX,example.com",
                    "surge_ruleset=🛑 广告拦截,[]DOMAIN,ads.example.com",
                )
            ),
            "shadowed",
        )[0]

        self.assertNotEqual(
            audit_rules.finding_signature(direct_winner), audit_rules.finding_signature(proxy_winner)
        )

    def test_baseline_round_trip(self):
        signature = "shadowed|a.list|DOMAIN-SUFFIX,ads.example.com|b.list|DOMAIN-SUFFIX,example.com|🚀 节点选择"
        with tempfile.TemporaryDirectory() as directory:
            path = audit_rules.pathlib.Path(directory) / "baseline.json"
            audit_rules.write_baseline(path, {signature})

            self.assertEqual(audit_rules.load_baseline(path), {signature})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["count"], 1)

    def test_missing_baseline_accepts_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = audit_rules.pathlib.Path(directory) / "absent.json"

            self.assertEqual(audit_rules.load_baseline(path), set())

    def test_committed_baseline_matches_the_current_tree(self):
        rules = audit_rules.collect_ranked_rules(
            audit_rules.CONFIG_FILE.read_text(encoding="utf-8").splitlines()
        )
        signatures = {audit_rules.finding_signature(finding) for finding in audit_rules.find_unreachable(rules)}
        baseline = audit_rules.load_baseline(audit_rules.REPO_ROOT / "audit-baseline.json")

        self.assertEqual(signatures - baseline, set(), "review the new conflicts, then --update-baseline")
        self.assertEqual(baseline - signatures, set(), "baseline still lists conflicts that no longer exist")


class PrivateLeakTests(unittest.TestCase):
    def test_private_domain_detection(self):
        self.assertTrue(audit_rules.is_private_domain("router.lan"))
        self.assertTrue(audit_rules.is_private_domain("localhost"))
        self.assertFalse(audit_rules.is_private_domain("example.com"))

    def test_leak_scan_covers_committed_lists_but_skips_sources(self):
        relative = [path.relative_to(audit_rules.REPO_ROOT) for path in audit_rules.iter_committed_list_files()]

        self.assertIn(audit_rules.pathlib.Path("Rules/Core/LocalAreaNetwork.list"), relative)
        self.assertNotIn(audit_rules.pathlib.Path("Rules/Core/ProxyManual.list"), relative)


if __name__ == "__main__":
    unittest.main()

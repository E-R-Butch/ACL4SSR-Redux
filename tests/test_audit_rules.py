import unittest

from scripts import audit_rules


GROUP_DEFINITIONS = [
    "custom_proxy_group=🎯 全球直连`select`[]DIRECT",
    "custom_proxy_group=🛑 广告拦截`select`[]REJECT",
    "custom_proxy_group=🔒 隐私保护`select`[]REJECT-DROP",
    "custom_proxy_group=🚀 节点选择`select`[]♻️ 自动选择",
]


def build_rules(*surge_lines):
    lines = GROUP_DEFINITIONS + list(surge_lines)
    return audit_rules.collect_ranked_rules(lines)


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

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(len(findings["duplicate"]), 1)
        self.assertIn("广告拦截", findings["duplicate"][0])

    def test_same_action_overlap_is_not_reported(self):
        rules = build_rules(
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,example.com",
            "surge_ruleset=🔒 隐私保护,[]DOMAIN,example.com",
        )

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(findings["duplicate"], [])

    def test_later_domain_covered_by_earlier_suffix(self):
        rules = build_rules(
            "surge_ruleset=🚀 节点选择,[]DOMAIN-SUFFIX,tracker.example",
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,ads.tracker.example",
        )

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(len(findings["shadowed"]), 1)
        self.assertIn("DOMAIN,ads.tracker.example", findings["shadowed"][0])

    def test_later_suffix_covered_by_earlier_parent_suffix(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]DOMAIN-SUFFIX,example.com",
            "surge_ruleset=🛑 广告拦截,[]DOMAIN-SUFFIX,ads.example.com",
        )

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(len(findings["shadowed"]), 1)

    def test_contained_network_with_matching_no_resolve_flag(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]IP-CIDR,203.0.113.0/24,no-resolve",
            "surge_ruleset=🛑 广告拦截,[]IP-CIDR,203.0.113.128/25,no-resolve",
        )

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(len(findings["contained"]), 1)

    def test_contained_network_without_matching_flag_is_not_reported(self):
        rules = build_rules(
            "surge_ruleset=🎯 全球直连,[]IP-CIDR,203.0.113.0/24,no-resolve",
            "surge_ruleset=🛑 广告拦截,[]IP-CIDR,203.0.113.128/25",
        )

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(findings["contained"], [])

    def test_rule_order_is_taken_from_the_ini_sequence(self):
        rules = build_rules(
            "surge_ruleset=🛑 广告拦截,[]DOMAIN,example.com",
            "surge_ruleset=🎯 全球直连,[]DOMAIN,example.com",
        )

        findings = audit_rules.find_unreachable(rules)

        self.assertEqual(len(findings["duplicate"]), 1)
        self.assertIn("全球直连", findings["duplicate"][0])


class PrivateLeakTests(unittest.TestCase):
    def test_private_domain_detection(self):
        self.assertTrue(audit_rules.is_private_domain("router.lan"))
        self.assertTrue(audit_rules.is_private_domain("localhost"))
        self.assertFalse(audit_rules.is_private_domain("example.com"))

    def test_private_leak_categories_cover_the_configured_list_dirs(self):
        relative = [path.relative_to(audit_rules.REPO_ROOT) for path in audit_rules.iter_committed_list_files()]

        self.assertIn(audit_rules.pathlib.Path("Rules/Core/LocalAreaNetwork.list"), relative)
        self.assertNotIn(audit_rules.pathlib.Path("Rules/Core/ProxyManual.list"), relative)


if __name__ == "__main__":
    unittest.main()

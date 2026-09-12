import pathlib
import re
import tempfile
import unittest

from scripts import validate_rules


ROOT = pathlib.Path(__file__).resolve().parents[1]
INI = ROOT / "Config/ACL4SSR_Online_Full.ini"


def render_members(definition, node_names):
    """Subconverter's documented plain regex and []literal group syntax."""
    members = []
    for selector in validate_rules.group_selectors(definition):
        if selector.startswith("[]"):
            members.append(selector[2:])
        else:
            members.extend(name for name in node_names if re.search(selector, name) and name not in members)
    return members or ["DIRECT"]  # Subconverter's empty-group behavior.


class RoutingSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.text = INI.read_text(encoding="utf-8")
        self.definitions = validate_rules.parse_custom_group_definitions(self.text.splitlines())

    def check_mutation(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "config.ini"
            path.write_text(text, encoding="utf-8")
            return validate_rules.validate_ini(path)

    def test_original_claude_indirect_direct_route_is_rejected(self):
        text = self.text.replace("🎭 Claude`select`[]🎭 Claude 自动", "🎭 Claude`select`[]🚀 节点选择")
        self.assertTrue(any("reaches DIRECT" in error for error in self.check_mutation(text)))

    def test_proxy_only_regex_group_cannot_fall_back_to_direct(self):
        definitions = {"🎭 Claude": "🎭 Claude`select`.*"}
        self.assertTrue(any("no nodes match" in error for error in validate_rules.validate_proxy_only_groups(definitions)))

    def test_claude_remains_proxy_only_with_mixed_unknown_or_no_nodes(self):
        for nodes in (["香港 Test", "日本 Test"], ["Unlabelled Test"], []):
            with self.subTest(nodes=nodes):
                groups = {name: render_members(value, nodes) for name, value in self.definitions.items()}
                pending, visited = ["🎭 Claude"], set()
                while pending:
                    name = pending.pop()
                    self.assertNotEqual(name, "DIRECT")
                    if name in visited:
                        continue
                    visited.add(name)
                    pending.extend(groups.get(name, []))

    def test_regions_contain_only_matching_nodes_or_reject(self):
        samples = {
            "🇩🇪 德国节点": "德国 Test", "🇭🇰 香港节点": "香港 Test",
            "🇯🇵 日本节点": "日本 Test", "🇺🇸 美国节点": "美国 Test",
            "🇨🇳 台湾节点": "台湾 Test", "🇸🇬 狮城节点": "新加坡 Test", "🇰🇷 韩国节点": "韩国 Test",
        }
        for group, node in samples.items():
            with self.subTest(group=group):
                self.assertEqual(render_members(self.definitions[group], list(samples.values())), [node, "REJECT"])
                self.assertEqual(render_members(self.definitions[group], ["Unlabelled Test"]), ["REJECT"])

    def test_global_member_in_region_is_rejected(self):
        old = self.definitions["🇭🇰 香港节点"]
        text = self.text.replace(old, old.replace("[]REJECT", "[]♻️ 自动选择"))
        self.assertTrue(any("region isolation" in error for error in self.check_mutation(text)))

    def test_netflix_regex_and_default_group_are_separate(self):
        members = render_members(self.definitions["🎥 奈飞视频"], ["NF Test", "Netflix Test", "普通节点"])
        self.assertIn("NF Test", members)
        self.assertIn("Netflix Test", members)
        self.assertIn("🚀 节点选择", members)
        self.assertNotIn("普通节点", members)

    def test_original_fused_netflix_regex_is_rejected(self):
        text = self.text.replace("|Media)`[]🚀 节点选择", "|Media)[]🚀 节点选择")
        self.assertTrue(any("invalid regex" in error for error in self.check_mutation(text)))

    def test_onedrive_first_domain_match_uses_dedicated_group(self):
        ordered = []
        for line in self.text.splitlines():
            if not line.startswith("surge_ruleset="):
                continue
            group, source = line.split("=", 1)[1].split(",", 1)
            path = validate_rules.local_path_from_raw_url(source)
            if path is None:
                continue
            for rule in path.read_text(encoding="utf-8").splitlines():
                if rule.startswith(("DOMAIN,", "DOMAIN-SUFFIX,", "DOMAIN-KEYWORD,")):
                    kind, value = rule.split(",")[:2]
                    ordered.append((kind, value, group))
        for host in ("onedrive.live.com", "photos.live.com", "storage.live.com", "skydrive.wns.windows.com", "api.1drv.com", "sharepoint.com"):
            with self.subTest(host=host):
                for kind, value, group in ordered:
                    matched = (kind == "DOMAIN" and host == value or
                               kind == "DOMAIN-SUFFIX" and (host == value or host.endswith("." + value)) or
                               kind == "DOMAIN-KEYWORD" and value in host)
                    if matched:
                        self.assertEqual(group, "Ⓜ️ 微软云盘")
                        break
                else:
                    self.fail(f"no rule matched {host}")

    def test_original_onedrive_precedence_is_rejected(self):
        lines = self.text.splitlines()
        a = next(i for i, line in enumerate(lines) if "/OneDrive.list" in line)
        b = next(i for i, line in enumerate(lines) if "/MicrosoftDirect.list" in line)
        lines[a], lines[b] = lines[b], lines[a]
        self.assertTrue(any("OneDrive.list must precede" in error for error in self.check_mutation("\n".join(lines))))

    def test_explicit_service_routes_preserve_existing_tracking_blocks(self):
        ordered = []
        for line in self.text.splitlines():
            if not line.startswith("surge_ruleset="):
                continue
            group, source = line.split("=", 1)[1].split(",", 1)
            if source.startswith("[]"):
                rules = [source[2:]]
            else:
                path = validate_rules.local_path_from_raw_url(source)
                rules = path.read_text(encoding="utf-8").splitlines() if path else []
            for rule in rules:
                if rule.startswith(("DOMAIN,", "DOMAIN-SUFFIX,", "DOMAIN-KEYWORD,")):
                    kind, value = rule.split(",")[:2]
                    ordered.append((kind, value, group))

        def first_policy(host):
            return next((
                group for kind, value, group in ordered
                if (kind == "DOMAIN" and host == value or
                    kind == "DOMAIN-SUFFIX" and (host == value or host.endswith("." + value)) or
                    kind == "DOMAIN-KEYWORD" and value in host)
            ), None)

        expected = {
            "www.ebay.com.hk": "🎯 全球直连",
            "ocswf.ebay.com.hk": "🎯 全球直连",
            "devicebind.ebay.com.hk": "🎯 全球直连",
            "www.ebay.com": "🎯 全球直连",
            "ir.ebaystatic.com": "🎯 全球直连",
            "cas.avalon.perfdrive.com": "🎯 全球直连",
            "global-help.ozon.com": "🎯 全球直连",
            "zh.zlib.li": "🚀 节点选择",
            "invalid": "REJECT",
            "this-url-does-not-exist-probe.invalid": "REJECT",
        }
        for host, policy in expected.items():
            with self.subTest(host=host):
                self.assertEqual(first_policy(host), policy)

        for host in ("epnt.ebay.com", "monitor.ebay.com", "pulsar.ebay.com"):
            with self.subTest(tracking_host=host):
                self.assertIn(first_policy(host), ("🛑 广告拦截", "🔒 隐私保护"))

    def test_ruleset_targets_accept_builtins_but_reject_unknown_names(self):
        self.assertEqual(self.check_mutation(self.text), [])
        text = self.text.replace("surge_ruleset=REJECT,[]DOMAIN-SUFFIX,invalid",
                                 "surge_ruleset=REJET,[]DOMAIN-SUFFIX,invalid")
        self.assertTrue(any("ruleset target 'REJET'" in error for error in self.check_mutation(text)))


if __name__ == "__main__":
    unittest.main()

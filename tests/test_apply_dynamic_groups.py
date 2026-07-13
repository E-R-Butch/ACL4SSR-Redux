import pathlib
import tempfile
import unittest

import yaml
from jinja2 import Environment

from scripts import apply_dynamic_groups


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def render_groups(proxy_remarks):
    environment = Environment(trim_blocks=True, lstrip_blocks=True)
    environment.filters["yaml"] = lambda value: yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    source = (
        (REPO_ROOT / "Config/DynamicRegionContext.j2").read_text(encoding="utf-8")
        + "\n"
        + (REPO_ROOT / "Config/DynamicProxyGroups.yml.j2").read_text(encoding="utf-8")
    )
    return yaml.safe_load(environment.from_string(source).render(proxy_remarks=proxy_remarks))


class DynamicGroupsTests(unittest.TestCase):
    def test_only_real_region_groups_are_rendered(self):
        config = render_groups(
            [
                "德国 | Test",
                "德国2 | Test",
                "日本Pro | Test",
                "美国 | Test",
                "日本Pro备用 | Test",
            ]
        )
        groups = {group["name"]: group for group in config["proxy-groups"]}

        self.assertEqual(groups["🇩🇪 德国节点"]["proxies"], ["德国 | Test", "德国2 | Test"])
        self.assertEqual(groups["🇯🇵 日本节点"]["proxies"], ["日本Pro | Test", "日本Pro备用 | Test"])
        self.assertEqual(groups["🇺🇸 美国节点"]["proxies"], ["美国 | Test"])
        self.assertNotIn("🇭🇰 香港节点", groups)
        self.assertNotIn("🇨🇳 台湾节点", groups)
        self.assertNotIn("🇸🇬 狮城节点", groups)
        self.assertNotIn("🇰🇷 韩国节点", groups)
        self.assertEqual(groups["🇭🇰 香港媒体"]["proxies"][0], "🚀 节点选择")
        self.assertNotIn("DIRECT", groups["🎭 Claude"]["proxies"])
        self.assertTrue(all(group.get("proxies") for group in groups.values()))

    def test_unknown_names_fall_back_without_empty_groups(self):
        config = render_groups(["Unlabelled Node"])
        groups = {group["name"]: group for group in config["proxy-groups"]}

        self.assertEqual(
            groups["🚀 节点选择"]["proxies"],
            ["♻️ 自动选择", "🚀 手动切换", "DIRECT"],
        )
        self.assertEqual(groups["🇯🇵 日本媒体"]["proxies"][0], "🚀 节点选择")
        self.assertTrue(all(group.get("proxies") for group in groups.values()))

    def test_replaces_only_context_and_group_sections(self):
        source = """# header
{% set all_proxies = proxy_remarks %}
{% set old = [] %}

mixed-port: 7890
proxies:
{{ conf.get("proxies", []) | yaml | indent(2, true) }}
proxy-groups:
  - name: old
    proxies:
      - DIRECT
rules:
  - MATCH,DIRECT
"""
        updated = apply_dynamic_groups.replace_dynamic_groups(
            source,
            "{% set all_proxies = proxy_remarks %}\n{% set marker = true %}",
            "proxy-groups:\n  - name: new\n    proxies:\n      - DIRECT",
        )
        self.assertIn("{% set marker = true %}", updated)
        self.assertIn("- name: new", updated)
        self.assertIn("- MATCH,DIRECT", updated)
        self.assertNotIn("- name: old", updated)


if __name__ == "__main__":
    unittest.main()

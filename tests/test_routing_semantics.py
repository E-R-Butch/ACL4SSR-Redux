import ipaddress
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

    def test_apple_relay_ipv6_routes_are_exact_and_wired_to_proxy(self):
        addresses = ("2620:149:af1::10", "2620:149:af6::10")
        for config_path in sorted((ROOT / "Config").glob("*.ini")):
            networks = []
            for line in config_path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("surge_ruleset="):
                    continue
                group, source = line.split("=", 1)[1].split(",", 1)
                path = validate_rules.local_path_from_raw_url(source)
                rules = [source[2:]] if source.startswith("[]") else path.read_text(encoding="utf-8").splitlines()
                for rule in rules:
                    if rule.startswith("IP-CIDR6,"):
                        parts = rule.split(",")
                        networks.append((ipaddress.ip_network(parts[1]), group, parts[2:]))

            for address in addresses:
                ip = ipaddress.ip_address(address)
                with self.subTest(config=config_path.name, address=address):
                    matched = next((entry for entry in networks if ip in entry[0]), None)
                    self.assertEqual(matched, (ipaddress.ip_network(address + "/128"), "🚀 节点选择", ["no-resolve"]))
                    for neighbor in (ip - 1, ip + 1):
                        self.assertFalse(any(neighbor in network for network, _, _ in networks))
            self.assertFalse(any(ipaddress.ip_address("2620:149:af0::10") in network for network, _, _ in networks))

    def test_web_service_routes_preserve_privacy_blocks_and_dedicated_ai_policies(self):
        expected = {
            "cdn.cookielaw.org": "🎯 全球直连",
            "cookies-data.onetrust.io": "🎯 全球直连",
            "geolocation.onetrust.com": "🎯 全球直连",
            "careers.amd.com": "🎯 全球直连",
            "app.jibecdn.com": "🎯 全球直连",
            "assets.jibecdn.com": "🎯 全球直连",
            "cms.jibecdn.com": "🎯 全球直连",
            "cdn02.icims.com": "🎯 全球直连",
            "f2pool.zendesk.com": "🎯 全球直连",
            "api.oaistatsig.com": "REJECT",
            "analytics.brew.sh": "REJECT",
            r"analytics.brew\.sh": "REJECT",
            "fast.fonts.net": "REJECT",
            "computerhistory.org": "🎯 全球直连",
            "www.computerhistory.org": "🚀 节点选择",
            r"www\.computerhistory.org": "🚀 节点选择",
            "images.fallout.wiki": "🎮 游戏代理",
            "commandcode.ai": "🚀 节点选择",
            "api.commandcode.ai": "🚀 节点选择",
            "r.jina.ai": "🚀 节点选择",
            "api.pullpush.io": "🚀 节点选择",
            "linustechtips.com": "🚀 节点选择",
            "forums.developer.nvidia.com": "🚀 节点选择",
            "ota.nvidia.com": "🚀 节点选择",
            "www.keebtalk.com": "🚀 节点选择",
            r"www\.keebtalk.com": "🚀 节点选择",
            "cdn.shopify.com": "🚀 节点选择",
            "easylist.to": "🚀 节点选择",
            "download.blender.org": "🚀 节点选择",
            "cua.ai": "🚀 节点选择",
            "models.dev": "🚀 节点选择",
            "eu.i.posthog.com": "REJECT",
            "aistacknav.com": "🚀 节点选择",
            "analytics.aistacknav.com": "REJECT",
            "wiki.eufymake.com": "🚀 节点选择",
            "openrgb.org": "🎯 全球直连",
            "softwareupdate.pilotmoon.com": "🚀 节点选择",
            "pilotmoon.com": "🚀 节点选择",
            "chub.ai": "🚀 节点选择",
            "gateway.chub.ai": "🚀 节点选择",
            "ro.chub.ai": "🎯 全球直连",
            "avatars.charhub.io": "🎯 全球直连",
            "odo.chub.ai": "REJECT",
            "code.trygravity.ai": "REJECT",
            "api.trygravity.ai": "REJECT",
            "cdn.humanbehavior.co": "REJECT",
            "ingest.humanbehavior.co": "REJECT",
            "artalk.bambulab.com": "🚀 节点选择",
            "static.cloudflareinsights.com": "REJECT",
            "portal.nousresearch.com": "🚀 节点选择",
            "hermes-agent.nousresearch.com": "🚀 节点选择",
            "openrouter.ai": "🚀 节点选择",
            "search.parallel.ai": "🎯 全球直连",
            "api.deps.dev": "🎯 全球直连",
            "cdn.simpleicons.org": "🎯 全球直连",
            "freebuff.com": "🚀 节点选择",
            "codebuff.com": "🚀 节点选择",
            "www.codebuff.com": "🚀 节点选择",
            "sstats.adobe.com": "REJECT",
            "auth.services.adobe.com": "🎯 全球直连",
            "acrobat.adobe.com": "🎯 全球直连",
            "api.paradox-interactive.com": "🎮 游戏直连",
            "revocation-prod.paradox-interactive.com": "🎮 游戏直连",
            "metadata-assets.paradox-interactive.com": "🎮 游戏代理",
            "distribution-fastly-prod.paradox-interactive.com": "🎮 游戏代理",
            "mods.paradoxplaza.com": "🎮 游戏代理",
            "www.paradoxinteractive.com": "🎮 游戏代理",
            r"www\.paradoxinteractive.com": "🎮 游戏代理",
            "launcher.paradoxinteractive.com": "🎮 游戏代理",
            "prod-telemetry.paradox-interactive.com": "REJECT",
            "rog-live-service.asus.com": "🚀 节点选择",
            "repository.certum.pl": "🎯 全球直连",
            "subca.repository.certum.pl": "🎯 全球直连",
            "crt.sectigo.com": "🎯 全球直连",
            "x1.c.lencr.org": "🎯 全球直连",
            "yr.c.lencr.org": "🎯 全球直连",
            "e8.c.lencr.org": "🎯 全球直连",
            "www.certum.eu": "🚀 节点选择",
            r"www\.certum.eu": "🚀 节点选择",
            "s3.us-west-1.wasabisys.com": "🚀 节点选择",
            "opencode.ai": "🚀 节点选择",
            "docs.macrocosmos.ai": "🎯 全球直连",
            "iota.macrocosmos.ai": "🎯 全球直连",
            "tah.iota.macrocosmos.ai": "🚀 节点选择",
            "ams3.digitaloceanspaces.com": "🚀 节点选择",
            "assets.crunchdao.com": "🚀 节点选择",
            "astral.sh": "🎯 全球直连",
            "releases.astral.sh": "🎯 全球直连",
            "www.desearch.ai": "🎯 全球直连",
            r"www\.desearch.ai": "🎯 全球直连",
            "www.gigabyte.com": "🚀 节点选择",
            r"www\.gigabyte.com": "🚀 节点选择",
            "static.gigabyte.com": "🎯 全球直连",
            "deprecated.png": "REJECT",
        }
        for config_path in sorted((ROOT / "Config").glob("*.ini")):
            ordered = []
            for line in config_path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("surge_ruleset="):
                    continue
                group, source = line.split("=", 1)[1].split(",", 1)
                if source.startswith("[]"):
                    rules = [source[2:]]
                else:
                    path = validate_rules.local_path_from_raw_url(source)
                    self.assertIsNotNone(path, f"unsupported ruleset source in {config_path.name}")
                    rules = path.read_text(encoding="utf-8").splitlines()
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

            for host, policy in expected.items():
                with self.subTest(config=config_path.name, service=host):
                    self.assertEqual(first_policy(host), policy)

            # The API exception must not move Steam downloads/images or Windows probes to proxy.
            for host, policy in {
                "api.steampowered.com": "🎮 游戏代理",
                "store.steampowered.com": "🎮 游戏代理",
                "steamcommunity.com": "🎮 游戏代理",
                "images.steamusercontent.com": "🎮 游戏直连",
                "cdn.steamusercontent.com": "🎮 游戏直连",
                "cdn.steamcontent.com": "🎮 游戏直连",
                "cdn.steamstatic.com": "🎮 游戏直连",
                "ipv6.msftconnecttest.com": "🎯 全球直连",
                "www.msftconnecttest.com": "🎯 全球直连",
                "dns.msftncsi.com": "🎯 全球直连",
            }.items():
                with self.subTest(config=config_path.name, steam_or_probe=host):
                    self.assertEqual(first_policy(host), policy)

            for host in (
                "smetrics.onetrust.com", "metrics.amd.com", "link.global.amd.com",
                "apac.zendesk.com", "go.zendesk.com", "join.zendesk.com",
                "metrics.nvidia.com", "smetrics.nvidia.com", "stt.nvidia.com",
                "prod.otel.kaizen.nvidia.com",
                "monorail-edge.shopifysvc.com", "stats.shopify.com", "v.shopify.com",
                "error-analytics-production.shopifysvc.com",
                "error-analytics-sessions-production.shopifysvc.com",
                "www.googletagmanager.com",
            ):
                with self.subTest(config=config_path.name, privacy_block=host):
                    self.assertEqual(first_policy(host), "🔒 隐私保护")

            # This exact host must be rejected before broad service routing.
            definitions = validate_rules.parse_custom_group_definitions(
                config_path.read_text(encoding="utf-8").splitlines())
            self.assertNotIn("📊 实验遥测", definitions)
            self.assertLess(
                next(i for i, entry in enumerate(ordered) if entry[1] == "api.oaistatsig.com"),
                next(i for i, entry in enumerate(ordered) if entry[2] == "🤖 OpenAI"))
            self.assertEqual(first_policy("chatgpt.com"), "🤖 OpenAI")
            self.assertEqual(first_policy("api.openai.com"), "🤖 OpenAI")
            self.assertEqual(first_policy("formulae.brew.sh"), "🚀 节点选择")
            self.assertEqual(first_policy("pagead2.googlesyndication.com"), "🛑 广告拦截")
            self.assertEqual(first_policy("www.google-analytics.com"), "🛑 广告拦截")
            # Blocking Cloudflare analytics must preserve challenge and CDN hosts.
            self.assertEqual(first_policy("challenges.cloudflare.com"), "🚀 节点选择")
            self.assertEqual(first_policy("cdnjs.cloudflare.com"), "🚀 节点选择")
            # MonitorControl's legitimate update host must precede the broad ad keyword.
            self.assertEqual(first_policy("monitorcontrol.app"), "🚀 节点选择")
            for host in ("child.monitorcontrol.app", "monitorcontrol.app.example", "monitor.ebay.com"):
                with self.subTest(config=config_path.name, monitor_exception_scope=host):
                    self.assertEqual(first_policy(host), "🛑 广告拦截")

            # The existing Claude suffix precedes the privacy list; retain that policy.
            with self.subTest(config=config_path.name, dedicated_ai="statsig.anthropic.com"):
                self.assertEqual(first_policy("statsig.anthropic.com"), "🎭 Claude")

            for host in (
                "random.zendesk.com", "unverified.onetrust.io", "unverified.onetrust.com",
                "unverified.cookielaw.org", "unverified.jibecdn.com", "unverified.icims.com",
                "unverified.oaistatsig.com", *("child." + host for host in expected),
                "other.chub.ai", "charhub.io", "other.charhub.io",
                "static.cloudflareinsights.com.example", "odo.chub.ai.example",
                "trygravity.ai", "other.trygravity.ai", "humanbehavior.co",
                "other.humanbehavior.co", "cdn.humanbehavior.co.example",
                "deps.dev", "other.deps.dev", "api.deps.dev.example",
                "simpleicons.org", "other.simpleicons.org",
                "other.freebuff.com", "other.codebuff.com", "codebuff.com.example",
                "bambulab.com", "wiki.bambulab.com", "forum.bambulab.com",
                "api.bambulab.com", "artalk.bambulab.com.example",
                "nousresearch.com", "inference-api.nousresearch.com",
                "eu.openrouter.ai", "us.openrouter.ai", "api.openrouter.ai",
                "openrouter.ai.example",
                "parallel.ai", "api.parallel.ai", "search.parallel.ai.example",
                "macrocosmos.ai", "unverified.macrocosmos.ai",
                "fra1.digitaloceanspaces.com", "sgp1.digitaloceanspaces.com",
                "unverified.ams3.digitaloceanspaces.com", "unverified.crunchdao.com",
                "api.desearch.ai", "unverified.gigabyte.com", "docs.astral.sh",
                "another.png",
                "brew.sh", "docs.brew.sh", "unverified.brew.sh", "analytics.brew.sh.example",
                "fonts.net", "other.fonts.net", "fast.fonts.net.example",
                "other.computerhistory.org", "fallout.wiki", "other.fallout.wiki",
                "unverified.commandcode.ai", "commandcode.ai.example",
                "api.commandcode.ai.example", "pullpush.io", "other.pullpush.io",
                "jina.ai", "s.jina.ai", "api.jina.ai",
                "other.linustechtips.com", "developer.nvidia.com", "other.nvidia.com",
                "ota-downloads.nvidia.com", "ota.nvidia.com.example",
                "keebtalk.com", "other.keebtalk.com", "www.keebtalk.com.example",
                "shopify.com", "other.shopify.com", "cdn.shopify.com.example",
                "www.easylist.to", "easylist.to.example",
                "blender.org", "www.blender.org", "download.blender.org.example",
                "www.cua.ai", "api.cua.ai", "run.cua.ai", "auth.cua.ai", "cua.ai.example",
                "api.models.dev", "models.dev.example", "posthog.com", "other.posthog.com",
                "www.aistacknav.com", "en.aistacknav.com", "geo.aistacknav.com",
                "aistacknav.com.example",
                "eufymake.com", "other.eufymake.com", "wiki.eufymake.com.example",
                "www.openrgb.org", "other.openrgb.org", "openrgb.org.example",
                "sstats.adobe.com.example",
                "paradox-interactive.com", "unverified.paradox-interactive.com",
                "paradoxinteractive.com", "unverified.paradoxinteractive.com",
                "paradoxplaza.com", "unverified.paradoxplaza.com",
                "rog-live-service.asus.com.example", "unverified.asus.com",
                "certum.pl", "unverified.certum.pl", "certum.eu", "unverified.certum.eu",
                "sectigo.com", "unverified.sectigo.com", "lencr.org", "unverified.c.lencr.org",
                "wasabisys.com", "s3.us-east-1.wasabisys.com", "s3.ap-northeast-1.wasabisys.com",
                "unverified.s3.us-west-1.wasabisys.com",
            ):
                with self.subTest(config=config_path.name, unverified_host=host):
                    self.assertIsNone(first_policy(host))


if __name__ == "__main__":
    unittest.main()

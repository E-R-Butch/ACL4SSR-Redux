import base64
import io
import ipaddress
import pathlib
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL_PROXY_FILE = REPO_ROOT / "Rules/Core/ProxyManual.list"

HAGEZI_BASE = "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/"
BLACKMATRIX_BASE = "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/"

# HaGeZi per-vendor native tracker lists: device and app telemetry, host level.
NATIVE_TRACKER_VENDORS = (
    "apple",
    "samsung",
    "xiaomi",
    "huawei",
    "oppo-realme",
    "vivo",
    "winoffice",
    "tiktok",
    "amazon",
    "lgwebos",
    "roku",
)

# blackmatrix7 service lists used below, by directory name.
BLACKMATRIX_LISTS = (
    "PlayStation",
    "Xbox",
    "EA",
    "Ubisoft",
    "Blizzard",
    "Riot",
    "Nintendo",
    "Discord",
    "Notion",
    "Jetbrains",
    "AppleID",
    "AppleMail",
    "AppleMusic",
    "Speedtest",
    "MicrosoftEdge",
)

# Lists whose rules are already decided elsewhere: a service bundle must not
# re-route a host an earlier list already matches, or re-add something that is
# blocked on purpose.
BLOCK_LISTS = (
    "Rules/Core/CustomReject.list",
    "Rules/Ruleset/Active/HardwareReject.list",
    "Rules/Ruleset/Active/AdobeReject.list",
    "Rules/Ruleset/Active/AppTelemetryReject.list",
    "Rules/Ruleset/Active/PCDNReject.list",
    "Rules/Outputs/MergedADBan.list",
    "Rules/Outputs/MergedPrivacy.list",
)

# Generated files that merge several upstream lists into one repository list.
BUNDLES = {
    "Rules/Ruleset/Active/AppTelemetryReject.list": {
        "label": "设备与应用内置遥测（HaGeZi native 追踪器清单）",
        "converter": "domains",
        "sources": tuple(f"HAGEZI_NATIVE_{vendor.upper().replace('-', '_')}" for vendor in NATIVE_TRACKER_VENDORS),
    },
    "Rules/Ruleset/Active/PCDNReject.list": {
        "label": "PCDN 节点（占用上行带宽）",
        "converter": "domains",
        "sources": ("ANTI_AD_PCDN",),
    },
    "Rules/Ruleset/Active/GamePlatform.list": {
        "label": "游戏平台账号、商店与联机服务",
        "converter": "clash",
        "sources": tuple(f"BLACKMATRIX_{name.upper()}" for name in ("PlayStation", "Xbox", "EA", "Ubisoft", "Blizzard", "Riot", "Nintendo")),
        "exclude": BLOCK_LISTS + ("Rules/Ruleset/Active/GameDirect.list", "Rules/Ruleset/Active/GameProxy.list"),
    },
    "Rules/Ruleset/Active/ChatProxy.list": {
        "label": "协作与聊天服务",
        "converter": "clash",
        "sources": tuple(f"BLACKMATRIX_{name.upper()}" for name in ("Discord", "Notion", "Jetbrains")),
        "exclude": BLOCK_LISTS + ("Rules/Ruleset/Active/CloudServiceProxy.list",),
    },
    "Rules/Ruleset/Active/AppleExtra.list": {
        "label": "Apple 账号、邮件与音乐",
        "converter": "clash",
        "sources": tuple(f"BLACKMATRIX_{name.upper()}" for name in ("AppleID", "AppleMail", "AppleMusic")),
        "exclude": BLOCK_LISTS + ("Rules/Ruleset/Active/AppleDirect.list", "Rules/Ruleset/Active/AppleProxy.list"),
    },
    "Rules/Ruleset/Active/ServiceDirectExtra.list": {
        "label": "测速与浏览器组件",
        "converter": "clash",
        "sources": tuple(f"BLACKMATRIX_{name.upper()}" for name in ("Speedtest", "MicrosoftEdge")),
        "exclude": BLOCK_LISTS
        + (
            "Rules/Ruleset/Active/MicrosoftDirect.list",
            # fast.com belongs to Netflix, which this repository proxies on purpose.
            "Rules/Ruleset/Active/Netflix.list",
            "Rules/Ruleset/Active/ProxyMedia.list",
        ),
    },
}

SOURCES = {
    "GFWLIST": "https://raw.githubusercontent.com/gfwlist/gfwlist/refs/heads/master/list.txt",
    "CHINA_IP": "https://raw.githubusercontent.com/mayaxcn/china-ip-list/refs/heads/master/chnroute.txt",
    "CHINA_IPV6": "https://raw.githubusercontent.com/mayaxcn/china-ip-list/refs/heads/master/chnroute_v6.txt",
    "EASYLIST": "https://easylist-downloads.adblockplus.org/easylist.txt",
    "EASYLIST_CHINA": "https://easylist-downloads.adblockplus.org/easylistchina.txt",
    "EASYPRIVACY": "https://easylist-downloads.adblockplus.org/easyprivacy.txt",
    "ANTI_AD_PCDN": "https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/discretion/pcdn.txt",
    "ANTI_AD_DOMAINS": "https://raw.githubusercontent.com/privacy-protection-tools/anti-AD/master/anti-ad-domains.txt",
    # Popularity list used to keep the Chinese ad increment from blocking sites
    # real people depend on; tranco-list.eu serves the top-1m as a zip.
    "TRANCO": "https://tranco-list.eu/top-1m.csv.zip",
    **{
        f"HAGEZI_NATIVE_{vendor.upper().replace('-', '_')}": f"{HAGEZI_BASE}native.{vendor}.txt"
        for vendor in NATIVE_TRACKER_VENDORS
    },
    **{f"BLACKMATRIX_{name.upper()}": f"{BLACKMATRIX_BASE}{name}/{name}.list" for name in BLACKMATRIX_LISTS},
}

# Sources fetched as bytes rather than decoded text.
BINARY_SOURCES = {"TRANCO"}
TRANCO_TOP_LIMIT = 1_000_000
ANTI_AD_TARGET = REPO_ROOT / "Rules/Ruleset/Active/AdBlock/BanAntiAD.list"

# Coverage is read from every committed list, minus these two. MergedADBan is
# derived from the ad ingredients *and* from yesterday's anti-AD increment, so
# letting it count as coverage would erase the increment on the next run; the
# increment itself is obviously not coverage for itself either.
COVERAGE_EXCLUDE_PATHS = (
    REPO_ROOT / "Rules/Outputs/MergedADBan.list",
    ANTI_AD_TARGET,
)
TARGETS = {
    "GFWLIST": REPO_ROOT / "Rules/Core/ProxyGFWlist.list",
    "CHINA_IP": REPO_ROOT / "Rules/Ruleset/Active/China/ChinaIp.list",
    "CHINA_IPV6": REPO_ROOT / "Rules/Ruleset/Active/China/ChinaIpV6.list",
    "EASYLIST": REPO_ROOT / "Rules/Ruleset/Active/AdBlock/BanEasyList.list",
    "EASYLIST_CHINA": REPO_ROOT / "Rules/Ruleset/Active/AdBlock/BanEasyListChina.list",
    "EASYPRIVACY": REPO_ROOT / "Rules/Ruleset/Active/AdBlock/BanEasyPrivacy.list",
}
ABP_METADATA = {
    "EASYLIST": "EasyList列表，只包含ABP中的 EasyList 内容",
    "EASYLIST_CHINA": "EasyListChina列表，只包含ABP中的 EasyListChina 内容",
    "EASYPRIVACY": "EasyPrivacy列表，隐私保护，屏蔽隐私追踪",
}
REQUEST_TIMEOUT = 30
REQUEST_ATTEMPTS = 3
USER_AGENT = "ACL4SSR-Redux-Rules-Sync/1.0 (+https://github.com/E-R-Butch/ACL4SSR-Redux)"


def log(message):
    print(f"[*] {message}", flush=True)


def fetch(url, attempts=REQUEST_ATTEMPTS, timeout=REQUEST_TIMEOUT):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            log(f"Fetching {url} (attempt {attempt}/{attempts})")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content = response.read().decode("utf-8")
            if not content.strip():
                raise ValueError("empty response")
            return content
        except (OSError, UnicodeError, ValueError, urllib.error.URLError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def decode_gfwlist(content):
    text = content.strip()
    if "[AutoProxy" in text:
        return text
    normalized = "".join(text.split())
    normalized += "=" * ((-len(normalized)) % 4)
    return base64.b64decode(normalized, validate=True).decode("utf-8", errors="strict")


def normalize_domain(value):
    value = re.sub(r"^[a-zA-Z]+://", "", value.strip())
    value = value.split("/", 1)[0].split(":", 1)[0].strip(".")
    if not value or any(character in value for character in ("*", " ", "%", "_")) or "." not in value:
        return None
    try:
        ipaddress.ip_address(value)
        return None
    except ValueError:
        pass
    labels = value.split(".")
    if any(
        not label
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-zA-Z0-9-]+", label)
        for label in labels
    ):
        return None
    return value.lower()


def extract_abp_host(rule_body):
    candidate = rule_body.strip()
    if not candidate or any(character in candidate for character in ("/", "*", "?")):
        return None
    if "^" in candidate:
        if not candidate.endswith("^"):
            return None
        candidate = candidate[:-1]
    return normalize_domain(candidate)


def parse_abp_domain_rule(rule):
    rule = rule.strip()
    if not rule or rule.startswith(("!", "[", "@@", "/", "#")) or "$" in rule:
        return None
    if rule.startswith("||"):
        domain = extract_abp_host(rule[2:])
        return f"DOMAIN-SUFFIX,{domain}" if domain else None
    if rule.startswith("|"):
        domain = extract_abp_host(rule[1:])
        return f"DOMAIN,{domain}" if domain else None
    if any(token in rule for token in ("*", "^", "##", "#@#", "#?#", "#$#")):
        return None
    domain = extract_abp_host(rule)
    return f"DOMAIN-SUFFIX,{domain}" if domain else None


def process_abp_list(content, source_key):
    rules = sorted(filter(None, {parse_abp_domain_rule(line) for line in content.splitlines()}))
    lines = [
        "# 广告列表 adblock rules",
        f"# 内容：{ABP_METADATA[source_key]}",
        f"# 来源：{SOURCES[source_key]}",
        f"# 数量：{len(rules)}条",
        "",
        *rules,
        "",
    ]
    log(f"Converted {source_key} into {len(rules)} Clash rules")
    return "\n".join(lines)


def convert_gfw_rule(line):
    line = line.strip()
    if not line or line.startswith(("!", "[", "@@", "/", "|http://127.0.0.1")):
        return None
    if line.startswith("||"):
        domain = normalize_domain(line[2:])
        return f"DOMAIN-SUFFIX,{domain}" if domain else None
    if line.startswith("|"):
        domain = normalize_domain(line[1:])
        return f"DOMAIN,{domain}" if domain else None
    domain = normalize_domain(line)
    return f"DOMAIN-SUFFIX,{domain}" if domain else None


def process_gfwlist(content, manual_path=MANUAL_PROXY_FILE):
    if not manual_path.is_file():
        raise FileNotFoundError(f"Manual proxy source is missing: {manual_path}")
    manual_lines = manual_path.read_text(encoding="utf-8").strip().splitlines()
    synced_rules = sorted(filter(None, {convert_gfw_rule(line) for line in decode_gfwlist(content).splitlines()}))
    lines = [
        "# 代理列表",
        "# 由 ProxyManual.list 与官方 GFWList 构建",
        "",
        *manual_lines,
        "",
        "# 官方同步：GFWList 产物",
        "# 这一段由脚本生成，请勿手工修改",
        *synced_rules,
        "",
    ]
    log(f"Converted GFWList into {len(synced_rules)} rules")
    return "\n".join(lines)


def process_ip(content, is_v6=False):
    version = 6 if is_v6 else 4
    prefix = "IP-CIDR6" if is_v6 else "IP-CIDR"
    networks = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        network = ipaddress.ip_network(line, strict=True)
        if network.version != version:
            raise ValueError(f"Expected IPv{version} network, got {line}")
        networks.add(str(network))
    lines = [
        f"# 内容：中国IPv{version}地址段",
        "",
        *[
            f"{prefix},{network},no-resolve"
            for network in sorted(
                networks,
                key=lambda value: (
                    int(ipaddress.ip_network(value).network_address),
                    ipaddress.ip_network(value).prefixlen,
                ),
            )
        ],
        "",
    ]
    return "\n".join(lines)


LIST_RULE_TOKENS = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6", "DST-PORT"}
KEYWORD_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")


def process_domain_lines(content):
    """Plain or wildcard domain lists (`*.host` or `host`) into DOMAIN-SUFFIX rules."""
    rules = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!", "[")):
            continue
        value = line[2:] if line.startswith("*.") else line
        domain = normalize_domain(value)
        if domain:
            rules.add(f"DOMAIN-SUFFIX,{domain}")
    return rules


def process_clash_rule_list(content, source_key):
    """Keep the domain/CIDR rules we can serve from a third-party Clash list."""
    rules = set()
    skipped = 0
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[1]:
            skipped += 1
            continue
        token = parts[0].upper()
        if token not in LIST_RULE_TOKENS:
            skipped += 1
            continue
        if token in {"IP-CIDR", "IP-CIDR6"}:
            try:
                network = ipaddress.ip_network(parts[1], strict=False)
            except ValueError:
                skipped += 1
                continue
            if network.is_private or network.is_loopback or network.is_link_local:
                skipped += 1
                continue
            modifier = ",no-resolve" if "no-resolve" in (part.lower() for part in parts[2:]) else ""
            rules.add(f"{token},{network}{modifier}")
            continue
        if token == "DOMAIN-KEYWORD":
            keyword = parts[1].lower().strip(".")
            if KEYWORD_PATTERN.match(keyword):
                rules.add(f"DOMAIN-KEYWORD,{keyword}")
            else:
                skipped += 1
            continue
        domain = normalize_domain(parts[1])
        if domain:
            rules.add(f"{token},{domain}")
        else:
            skipped += 1
    if skipped:
        log(f"Skipped {skipped} unsupported rule(s) from {source_key}")
    return rules


def rule_key(rule):
    parts = [part.strip() for part in rule.split(",")]
    if len(parts) < 2 or not parts[1]:
        return None
    return parts[0].upper(), parts[1].lower().rstrip(".")


def read_existing_rule_keys(relative_paths):
    keys = set()
    for relative in relative_paths:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key = rule_key(line)
            if key:
                keys.add(key)
    return keys


def is_decided_elsewhere(rule, excluded_keys):
    """A candidate is dropped when an earlier list already routes it identically."""
    key = rule_key(rule)
    if key is None:
        return False
    if key in excluded_keys:
        return True
    rule_type, value = key
    if rule_type != "DOMAIN":
        return False
    labels = value.split(".")
    for start in range(len(labels) - 1):
        if ("DOMAIN-SUFFIX", ".".join(labels[start:])) in excluded_keys:
            return True
    return False


def process_bundle(bundle, fetched):
    rules = set()
    for source_key in bundle["sources"]:
        content = fetched[source_key]
        if bundle["converter"] == "domains":
            rules |= process_domain_lines(content)
        else:
            rules |= process_clash_rule_list(content, source_key)

    excluded = read_existing_rule_keys(bundle.get("exclude", ()))
    if excluded:
        before = len(rules)
        rules = {rule for rule in rules if not is_decided_elsewhere(rule, excluded)}
        log(f"Excluded {before - len(rules)} rule(s) already decided by earlier lists")

    lines = [
        f"# 内容：{bundle['label']}",
        "# 来源：" + " , ".join(SOURCES[source_key] for source_key in bundle["sources"]),
        f"# 数量：{len(rules)}条",
        "",
        *sorted(rules),
        "",
    ]
    log(f"Built {len(rules)} rule(s) for {bundle['label']}")
    return "\n".join(lines)


def fetch_binary(url, attempts=REQUEST_ATTEMPTS, timeout=REQUEST_TIMEOUT):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            log(f"Fetching {url} (attempt {attempt}/{attempts})")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content = response.read()
            if not content:
                raise ValueError("empty response")
            return content
        except (OSError, ValueError, urllib.error.URLError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Unable to fetch {url}: {last_error}")


def read_tranco_registrable(zip_bytes, limit=TRANCO_TOP_LIMIT):
    """Registrable domains of the most popular sites, from the Tranco zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        name = archive.namelist()[0]
        text = archive.read(name).decode("utf-8", errors="replace")
    popular = set()
    for line in text.splitlines():
        fields = line.strip().split(",")
        if len(fields) != 2:
            continue
        try:
            rank = int(fields[0])
        except ValueError:
            continue
        if rank > limit:
            break
        domain = normalize_domain(fields[1])
        if domain:
            popular.add(registrable_domain(domain))
    log(f"Tranco: {len(popular)} popular registrable domain(s) within rank {limit}")
    return popular


SECOND_LEVEL_SUFFIXES = {
    "ac", "co", "com", "edu", "go", "gov", "net", "ne", "or", "org",
}


def registrable_domain(domain):
    """Approximate registrable domain, aware of the common two-part TLDs."""
    labels = domain.split(".")
    if len(labels) <= 2:
        return domain
    if labels[-2] in SECOND_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def repo_rule_values(exclude_paths=()):
    """Every rule value already present under Rules/, i.e. already decided."""
    excluded = {path.resolve() for path in exclude_paths}
    values = set()
    for path in sorted((REPO_ROOT / "Rules").rglob("*.list")):
        if path.resolve() in excluded:
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 2 and parts[0].upper().startswith(("DOMAIN", "IP-CIDR")):
                values.add(parts[1].lower().rstrip("."))
    return values


def is_value_covered(value, values):
    if value in values:
        return True
    labels = value.split(".")
    return any(".".join(labels[start:]) in values for start in range(1, len(labels)))


def process_anti_ad(content, popular, decided):
    """Chinese ad increment: only what nothing else covers and popularity allows."""
    candidates = set()
    for line in content.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        domain = normalize_domain(line)
        if domain:
            candidates.add(domain)
    covered = {value for value in candidates if is_value_covered(value, decided)}
    remaining = candidates - covered
    popular_skipped = {value for value in remaining if registrable_domain(value) in popular}
    rules = sorted(f"DOMAIN-SUFFIX,{value}" for value in remaining - popular_skipped)

    log(
        f"anti-AD: {len(candidates)} candidate(s), {len(covered)} already covered, "
        f"{len(popular_skipped)} inside the popular-domain list, {len(rules)} kept"
    )
    lines = [
        "# 广告列表 adblock rules",
        "# 内容：中文广告与隐私域名增量（anti-AD 减去本项目已覆盖部分与热门站点）",
        f"# 来源：{SOURCES['ANTI_AD_DOMAINS']} + {SOURCES['TRANCO']}",
        f"# 数量：{len(rules)}条",
        "",
        *rules,
        "",
    ]
    return "\n".join(lines)


def build_outputs(fetched, popular=()):
    outputs = {
        TARGETS["GFWLIST"]: process_gfwlist(fetched["GFWLIST"]),
        TARGETS["EASYLIST"]: process_abp_list(fetched["EASYLIST"], "EASYLIST"),
        TARGETS["EASYLIST_CHINA"]: process_abp_list(fetched["EASYLIST_CHINA"], "EASYLIST_CHINA"),
        TARGETS["EASYPRIVACY"]: process_abp_list(fetched["EASYPRIVACY"], "EASYPRIVACY"),
        TARGETS["CHINA_IP"]: process_ip(fetched["CHINA_IP"]),
        TARGETS["CHINA_IPV6"]: process_ip(fetched["CHINA_IPV6"], is_v6=True),
        ANTI_AD_TARGET: process_anti_ad(fetched["ANTI_AD_DOMAINS"], popular, repo_rule_values(COVERAGE_EXCLUDE_PATHS)),
    }
    for relative, bundle in BUNDLES.items():
        outputs[REPO_ROOT / relative] = process_bundle(bundle, fetched)
    return outputs


def install_outputs(outputs):
    with tempfile.TemporaryDirectory(prefix=".rule-sync-", dir=REPO_ROOT) as temp_dir:
        staging_root = pathlib.Path(temp_dir)
        staged = []
        for target, content in outputs.items():
            relative = target.relative_to(REPO_ROOT)
            staged_path = staging_root / relative
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_text(content, encoding="utf-8")
            staged.append((staged_path, target))
        for staged_path, target in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_path), target)


def main():
    log("Asset Fetcher Started")
    fetched = {key: fetch(url) for key, url in SOURCES.items() if key not in BINARY_SOURCES}
    popular = read_tranco_registrable(fetch_binary(SOURCES["TRANCO"]))
    outputs = build_outputs(fetched, popular)
    install_outputs(outputs)
    log("Asset Fetcher Completed")


if __name__ == "__main__":
    main()

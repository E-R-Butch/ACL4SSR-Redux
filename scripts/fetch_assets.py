import base64
import ipaddress
import pathlib
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MANUAL_PROXY_FILE = REPO_ROOT / "Rules/Core/ProxyManual.list"
SOURCES = {
    "GFWLIST": "https://raw.githubusercontent.com/gfwlist/gfwlist/refs/heads/master/list.txt",
    "CHINA_IP": "https://raw.githubusercontent.com/mayaxcn/china-ip-list/refs/heads/master/chnroute.txt",
    "CHINA_IPV6": "https://raw.githubusercontent.com/mayaxcn/china-ip-list/refs/heads/master/chnroute_v6.txt",
    "EASYLIST": "https://easylist-downloads.adblockplus.org/easylist.txt",
    "EASYLIST_CHINA": "https://easylist-downloads.adblockplus.org/easylistchina.txt",
    "EASYPRIVACY": "https://easylist-downloads.adblockplus.org/easyprivacy.txt",
}
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
USER_AGENT = "ACL4SSR-Neo-Rules-Sync/1.0 (+https://github.com/E-R-Butch/ACL4SSR-Neo)"


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


def build_outputs(fetched):
    return {
        TARGETS["GFWLIST"]: process_gfwlist(fetched["GFWLIST"]),
        TARGETS["EASYLIST"]: process_abp_list(fetched["EASYLIST"], "EASYLIST"),
        TARGETS["EASYLIST_CHINA"]: process_abp_list(fetched["EASYLIST_CHINA"], "EASYLIST_CHINA"),
        TARGETS["EASYPRIVACY"]: process_abp_list(fetched["EASYPRIVACY"], "EASYPRIVACY"),
        TARGETS["CHINA_IP"]: process_ip(fetched["CHINA_IP"]),
        TARGETS["CHINA_IPV6"]: process_ip(fetched["CHINA_IPV6"], is_v6=True),
    }


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
    fetched = {source_key: fetch(url) for source_key, url in SOURCES.items()}
    outputs = build_outputs(fetched)
    install_outputs(outputs)
    log("Asset Fetcher Completed")


if __name__ == "__main__":
    main()

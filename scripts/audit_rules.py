"""Audit rule quality against the real match order of the main ini.

The main configuration resolves rules top-down: the first rule that matches a
connection wins. Two consequences drive this audit:

* A rule that is unreachable (an earlier rule with a *different action* already
  matches everything it matches) is dead weight at best and a silent routing
  change at worst - for example a privacy block that never fires because the
  parent domain was matched by a direct or proxy rule first.
* Overlaps whose earlier rule lands in the same action class (REJECT vs
  REJECT-DROP, or two ad sources merged into one output) change nothing, so
  they are not reported.

Only rule sources referenced by the ini are ranked, which excludes build
ingredients such as the AdBlock sources: their output is what actually routes
traffic, so comparing an ingredient with its own output is meaningless.
"""

import argparse
import ipaddress
import pathlib
import re
import sys
from collections import defaultdict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

CONFIG_FILE = REPO_ROOT / "Config/ACL4SSR_Online_Full.ini"
LIST_DIRS = [
    REPO_ROOT / "Rules/Core",
    REPO_ROOT / "Rules/Outputs",
    REPO_ROOT / "Rules/Ruleset/Active",
]
RAW_PREFIX = "https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Redux/master/"

SOURCE_ONLY_FILES = {
    pathlib.Path("Rules/Core/ProxyManual.list"),
}

PRIVATE_ALLOWED_FILES = {
    pathlib.Path("Rules/Core/LocalAreaNetwork.list"),
}

SPECIAL_ACTIONS = {
    "DIRECT": "direct",
    "REJECT": "block",
    "REJECT-DROP": "block",
}

PRIVATE_DOMAIN_SUFFIXES = (
    ".lan",
    ".local",
    ".localhost",
    ".home",
    ".internal",
    ".intranet",
)

LOCALHOST_NAMES = {
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
}

NETWORK_TYPES = {"IP-CIDR", "IP-CIDR6"}
DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX"}


def log(message):
    print(f"[*] {message}", flush=True)


def warn(message):
    print(f"[!] {message}", flush=True)


def parse_group_actions(lines):
    """Map every proxy group name to its action class: block / direct / proxy."""
    actions = {"DIRECT": "direct", "REJECT": "block", "REJECT-DROP": "block"}
    for line in lines:
        if not line.startswith("custom_proxy_group="):
            continue
        fields = line[len("custom_proxy_group="):].split("`")
        name = fields[0].strip()
        members = fields[2] if len(fields) > 2 else ""
        tokens = [token.strip() for token in re.findall(r"\[\](\S+)", members)]
        if tokens and tokens[0] in SPECIAL_ACTIONS:
            actions[name] = SPECIAL_ACTIONS[tokens[0]]
        else:
            actions[name] = "proxy"
    return actions


def list_path_from_url(url):
    if not url.startswith(RAW_PREFIX):
        return None
    return REPO_ROOT / url[len(RAW_PREFIX):]


def parse_match_order(lines):
    """Return ranked rule sources in the order the ini matches them."""
    sources = []
    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line.startswith("surge_ruleset="):
            continue
        target, _, remainder = line[len("surge_ruleset="):].partition(",")
        target = target.strip()
        remainder = remainder.strip()

        if remainder.startswith("[]"):
            sources.append((len(sources), target, None, [(remainder[2:].strip(), lineno)]))
            continue

        path = list_path_from_url(remainder)
        if path is None:
            log(f"Skipping unparsed surge_ruleset at {CONFIG_FILE.name}:{lineno}")
            continue

        rules = []
        if path.exists():
            for offset, source_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                source_line = source_line.strip()
                if source_line and not source_line.startswith("#") and "," in source_line:
                    rules.append((source_line, offset))
        sources.append((len(sources), target, path, rules))
    return sources


def parse_rule(raw, lineno, rank, target, action, path):
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) < 2 or not parts[1]:
        return None
    rule_type = parts[0].upper()
    value = parts[1].lower().rstrip(".")
    no_resolve = "no-resolve" in (part.lower() for part in parts[2:])
    network = None
    if rule_type in NETWORK_TYPES:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            network = None
    return {
        "rank": rank,
        "target": target,
        "action": action,
        "path": path,
        "line": lineno,
        "type": rule_type,
        "value": value,
        "raw": raw,
        "no_resolve": no_resolve,
        "network": network,
    }


def collect_ranked_rules(lines):
    actions = parse_group_actions(lines)
    rules = []
    for rank, target, path, source_rules in parse_match_order(lines):
        action = actions.get(target, "proxy")
        for raw, lineno in source_rules:
            rule = parse_rule(raw, lineno, rank, target, action, path)
            if rule:
                rules.append(rule)
    return rules


def location(rule):
    if rule["path"] is None:
        return f"{CONFIG_FILE.name}:{rule['line']}"
    try:
        return f"{rule['path'].relative_to(REPO_ROOT)}:{rule['line']}"
    except ValueError:
        return f"{rule['path']}:{rule['line']}"


def describe(rule):
    return f"{rule['raw']} -> {rule['target']}[{rule['action']}] @{location(rule)}"


def find_unreachable(rules):
    """Rules that can never match because an earlier rule already covers them."""
    findings = defaultdict(list)

    def add(category, message):
        findings[category].append(message)

    first_match = {}
    for rule in rules:
        first_match.setdefault((rule["type"], rule["value"]), rule)

    for rule in rules:
        winner = first_match[(rule["type"], rule["value"])]
        if winner["rank"] < rule["rank"] and winner["action"] != rule["action"]:
            add("duplicate", f"{describe(rule)} already matched by {describe(winner)}")

    suffix_first = {}
    for rule in rules:
        if rule["type"] == "DOMAIN-SUFFIX":
            suffix_first.setdefault(rule["value"], rule)

    for rule in rules:
        if rule["type"] not in DOMAIN_TYPES:
            continue
        labels = rule["value"].split(".")
        for index in range(len(labels) - 1):
            ancestor = ".".join(labels[index:])
            if ancestor == rule["value"] and rule["type"] == "DOMAIN-SUFFIX":
                continue
            winner = suffix_first.get(ancestor)
            if not winner or winner["rank"] >= rule["rank"] or winner["action"] == rule["action"]:
                continue
            add("shadowed", f"{describe(rule)} covered by {describe(winner)}")
            break

    network_first = {}
    for rule in rules:
        network = rule["network"]
        if network is not None:
            network_first.setdefault((network.version, str(network), rule["no_resolve"]), rule)

    for rule in rules:
        network = rule["network"]
        if network is None:
            continue
        for prefix_length in range(network.prefixlen - 1, -1, -1):
            supernet = network.supernet(new_prefix=prefix_length)
            winner = network_first.get((supernet.version, str(supernet), rule["no_resolve"]))
            if winner and winner["rank"] < rule["rank"] and winner["action"] != rule["action"]:
                add("contained", f"{describe(rule)} inside {describe(winner)}")
                break

    return findings


def iter_committed_list_files():
    for list_dir in LIST_DIRS:
        if not list_dir.exists():
            continue
        for path in sorted(list_dir.rglob("*.list")):
            relative = path.relative_to(REPO_ROOT)
            if relative in SOURCE_ONLY_FILES:
                continue
            yield path


def is_private_domain(value):
    return value in LOCALHOST_NAMES or value.endswith(PRIVATE_DOMAIN_SUFFIXES)


def find_private_leaks():
    findings = []
    for path in iter_committed_list_files():
        relative = path.relative_to(REPO_ROOT)
        if relative in PRIVATE_ALLOWED_FILES:
            continue
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or "," not in line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2 or not parts[1]:
                continue
            rule_type = parts[0].upper()
            value = parts[1].lower().rstrip(".")
            where = f"{relative}:{lineno}"
            if rule_type in DOMAIN_TYPES and is_private_domain(value):
                findings.append(f"private/local domain in public rule: {line} at {where}")
            if rule_type in NETWORK_TYPES:
                try:
                    network = ipaddress.ip_network(value, strict=False)
                except ValueError:
                    continue
                if network.is_private or network.is_loopback or network.is_link_local:
                    findings.append(f"private/local ip range in public rule: {line} at {where}")
    return findings


def print_section(title, findings, limit):
    log(title)
    if not findings:
        print("  OK", flush=True)
        return
    for finding in findings[:limit]:
        warn(finding)
    if len(findings) > limit:
        print(f"  ... +{len(findings) - limit} more", flush=True)


CATEGORIES = ("duplicate", "shadowed", "contained")


def main():
    parser = argparse.ArgumentParser(
        description="Audit rules against the ini match order for unreachable rules and private leakage."
    )
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any finding is reported.")
    parser.add_argument("--max-findings", type=int, default=50, help="Maximum findings printed per category.")
    args = parser.parse_args()

    lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines()
    rules = collect_ranked_rules(lines)
    log(f"Ranked {len(rules)} rule(s) across {len(parse_match_order(lines))} source(s)")

    unreachable = find_unreachable(rules)
    flat = []
    for category in CATEGORIES:
        for message in unreachable[category]:
            flat.append(f"[{category}] {message}")

    sections = [
        ("Unreachable rules (earlier rule with a different action wins)", flat),
        ("Private/local rule leakage", find_private_leaks()),
    ]

    total = 0
    for title, findings in sections:
        total += len(findings)
        print_section(title, findings, args.max_findings)

    if total:
        summary = ", ".join(f"{category}={len(unreachable[category])}" for category in CATEGORIES)
        warn(f"Audit completed with {total} finding(s) ({summary})")
        if args.strict:
            sys.exit(1)
    else:
        log("Audit completed with no findings.")


if __name__ == "__main__":
    main()

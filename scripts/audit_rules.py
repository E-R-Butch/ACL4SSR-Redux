import argparse
import ipaddress
import pathlib
import sys
from collections import defaultdict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LIST_DIRS = [
    REPO_ROOT / "Rules/Core",
    REPO_ROOT / "Rules/Outputs",
    REPO_ROOT / "Rules/Ruleset/Active",
    REPO_ROOT / "Rules/Ruleset/Inactive",
]

PRIVATE_ALLOWED_FILES = {
    pathlib.Path("Rules/Core/LocalAreaNetwork.list"),
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


def log(message):
    print(f"[*] {message}", flush=True)


def warn(message):
    print(f"[!] {message}", flush=True)


def iter_list_files():
    for list_dir in LIST_DIRS:
        if not list_dir.exists():
            continue
        yield from sorted(list_dir.rglob("*.list"))


def parse_rule(raw_line):
    line = raw_line.strip()
    if not line or line.startswith("#") or "," not in line:
        return None

    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 2:
        return None

    return {
        "line": line,
        "type": parts[0].upper(),
        "value": parts[1].lower().rstrip("."),
    }


def collect_rules():
    rules = []
    for path in iter_list_files():
        rel_path = path.relative_to(REPO_ROOT)
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            parsed = parse_rule(raw_line)
            if not parsed:
                continue
            parsed["path"] = rel_path
            parsed["lineno"] = lineno
            rules.append(parsed)
    return rules


def location(rule):
    return f"{rule['path']}:{rule['lineno']}"


def find_cross_file_duplicates(rules, max_findings):
    by_line = defaultdict(list)
    for rule in rules:
        by_line[rule["line"]].append(rule)

    findings = []
    for line, matches in sorted(by_line.items()):
        paths = {match["path"] for match in matches}
        if len(paths) <= 1:
            continue
        locs = ", ".join(location(match) for match in matches[:4])
        if len(matches) > 4:
            locs += f", ... +{len(matches) - 4} more"
        findings.append(f"duplicate rule across files: {line} ({locs})")
        if len(findings) >= max_findings:
            break
    return findings


def find_domain_suffix_coverage(rules, max_findings):
    suffix_rules = [rule for rule in rules if rule["type"] == "DOMAIN-SUFFIX" and rule["value"]]
    domain_rules = [rule for rule in rules if rule["type"] == "DOMAIN" and rule["value"]]

    suffixes_by_tail = defaultdict(list)
    for suffix_rule in suffix_rules:
        labels = suffix_rule["value"].split(".")
        if labels:
            suffixes_by_tail[labels[-1]].append(suffix_rule)

    findings = []
    for domain_rule in domain_rules:
        labels = domain_rule["value"].split(".")
        if not labels:
            continue
        for suffix_rule in suffixes_by_tail.get(labels[-1], []):
            suffix = suffix_rule["value"]
            domain = domain_rule["value"]
            if domain == suffix or domain.endswith(f".{suffix}"):
                findings.append(
                    "domain covered by suffix: "
                    f"{domain_rule['line']} at {location(domain_rule)} "
                    f"covered by {suffix_rule['line']} at {location(suffix_rule)}"
                )
                break
        if len(findings) >= max_findings:
            break
    return findings


def parse_network(rule):
    if rule["type"] not in {"IP-CIDR", "IP-CIDR6"}:
        return None
    try:
        return ipaddress.ip_network(rule["value"], strict=False)
    except ValueError:
        return None


def find_ip_containment(rules, max_findings):
    network_rules = []
    for rule in rules:
        network = parse_network(rule)
        if network:
            network_rules.append((network, rule))

    findings = []
    for index, (network, rule) in enumerate(network_rules):
        for other_network, other_rule in network_rules[index + 1 :]:
            if network.version != other_network.version:
                continue
            if network == other_network:
                continue
            if network.supernet_of(other_network):
                findings.append(
                    "ip cidr contained by broader rule: "
                    f"{other_rule['line']} at {location(other_rule)} "
                    f"inside {rule['line']} at {location(rule)}"
                )
            elif other_network.supernet_of(network):
                findings.append(
                    "ip cidr contained by broader rule: "
                    f"{rule['line']} at {location(rule)} "
                    f"inside {other_rule['line']} at {location(other_rule)}"
                )
            if len(findings) >= max_findings:
                return findings
    return findings


def is_private_domain(value):
    return value in LOCALHOST_NAMES or value.endswith(PRIVATE_DOMAIN_SUFFIXES)


def find_private_leaks(rules, max_findings):
    findings = []
    for rule in rules:
        if rule["path"] in PRIVATE_ALLOWED_FILES:
            continue

        if rule["type"] in {"DOMAIN", "DOMAIN-SUFFIX"} and is_private_domain(rule["value"]):
            findings.append(f"private/local domain in public rule: {rule['line']} at {location(rule)}")

        network = parse_network(rule)
        if network and (network.is_private or network.is_loopback or network.is_link_local):
            findings.append(f"private/local ip range in public rule: {rule['line']} at {location(rule)}")

        if len(findings) >= max_findings:
            break
    return findings


def print_section(title, findings):
    log(title)
    if not findings:
        print("  OK", flush=True)
        return
    for finding in findings:
        warn(finding)


def main():
    parser = argparse.ArgumentParser(description="Report optional rule quality audit findings.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any finding is reported.")
    parser.add_argument("--max-findings", type=int, default=50, help="Maximum findings per audit category.")
    args = parser.parse_args()

    rules = collect_rules()
    log(f"Loaded {len(rules)} effective rule(s)")

    sections = [
        ("Cross-file duplicate rules", find_cross_file_duplicates(rules, args.max_findings)),
        ("DOMAIN rules covered by DOMAIN-SUFFIX", find_domain_suffix_coverage(rules, args.max_findings)),
        ("IP CIDR containment", find_ip_containment(rules, args.max_findings)),
        ("Private/local rule leakage", find_private_leaks(rules, args.max_findings)),
    ]

    total_findings = 0
    for title, findings in sections:
        total_findings += len(findings)
        print_section(title, findings)

    if total_findings:
        warn(f"Audit completed with {total_findings} finding(s).")
        if args.strict:
            sys.exit(1)
    else:
        log("Audit completed with no findings.")


if __name__ == "__main__":
    main()

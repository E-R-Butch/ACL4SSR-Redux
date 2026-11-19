import argparse
import hashlib
import ipaddress
import json
import os
import pathlib
import tempfile
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_DROP_RATIO = 0.30
MAX_GROWTH_RATIO = 1.00

TARGETS = {
    "Rules/Core/ProxyGFWlist.list": 1000,
    "Rules/Ruleset/Active/AdBlock/BanEasyList.list": 10000,
    "Rules/Ruleset/Active/AdBlock/BanEasyListChina.list": 1000,
    "Rules/Ruleset/Active/AdBlock/BanEasyPrivacy.list": 10000,
    "Rules/Ruleset/Active/AdBlock/BanAntiAD.list": 8000,
    "Rules/Ruleset/Active/China/ChinaIp.list": 1000,
    "Rules/Ruleset/Active/China/ChinaIpV6.list": 100,
    "Rules/Ruleset/Active/AppTelemetryReject.list": 2500,
    "Rules/Ruleset/Active/PCDNReject.list": 20,
    "Rules/Ruleset/Active/GamePlatform.list": 350,
    "Rules/Ruleset/Active/ChatProxy.list": 35,
    "Rules/Ruleset/Active/AppleExtra.list": 4,
    "Rules/Ruleset/Active/ServiceDirectExtra.list": 8,
}

# These lists contain a single action selected by the unchanged INI, and every
# rule has the same no-resolve modifier. Compare address sets, not CIDR counts.
IP_TARGETS = {
    "Rules/Ruleset/Active/China/ChinaIp.list": 4,
    "Rules/Ruleset/Active/China/ChinaIpV6.list": 6,
}
MAX_REVIEW_LOG_NETWORKS = 20
MAX_REVIEW_SUMMARY_BYTES = 800_000

BAD_CONTENT_MARKERS = (
    "<html",
    "<!doctype",
    "404:",
    "404 not found",
    "rate limit",
    "too many requests",
)


def log(message):
    print(f"[*] {message}", flush=True)


def fail(message):
    print(f"[!] {message}", flush=True)


def is_effective_rule(line):
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("#"))


def count_effective_rules(text):
    return sum(1 for line in text.splitlines() if is_effective_rule(line))


def read_head_text(rel_path):
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def looks_like_error_page(text):
    lowered = text[:8192].lower()
    return any(marker in lowered for marker in BAD_CONTENT_MARKERS)


def validate_target(rel_path, min_rules):
    path = REPO_ROOT / rel_path
    if path.is_symlink() or not path.is_file():
        return [f"{rel_path}: missing or non-regular generated rule file"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"{rel_path}: {error}"]
    errors = []

    if looks_like_error_page(text):
        errors.append(f"{rel_path}: content looks like an upstream error page")

    rule_count = count_effective_rules(text)
    log(f"{rel_path}: {rule_count} effective rule(s), minimum {min_rules}")
    if rule_count < min_rules:
        errors.append(f"{rel_path}: only {rule_count} effective rule(s), expected at least {min_rules}")

    head_text = read_head_text(rel_path)
    if head_text is not None:
        previous_count = count_effective_rules(head_text)
        log(f"{rel_path}: previous baseline {previous_count} effective rule(s)")
        if previous_count > 0:
            min_allowed = int(previous_count * (1 - MAX_DROP_RATIO))
            max_allowed = int(previous_count * (1 + MAX_GROWTH_RATIO))
            if rule_count < min_allowed:
                errors.append(
                    f"{rel_path}: rule count dropped from {previous_count} to {rule_count}, "
                    f"exceeding {MAX_DROP_RATIO:.0%} guardrail"
                )
            if rule_count > max_allowed:
                errors.append(
                    f"{rel_path}: rule count grew from {previous_count} to {rule_count}, "
                    f"exceeding {MAX_GROWTH_RATIO:.0%} guardrail"
                )

    return errors


def parse_ip_rules(text, version):
    """Strictly accept only the homogeneous CIDR form used by these two lists."""
    if looks_like_error_page(text):
        raise ValueError("content looks like an upstream error page")
    prefix = "IP-CIDR6" if version == 6 else "IP-CIDR"
    networks = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not is_effective_rule(raw):
            continue
        parts = raw.strip().split(",")
        if len(parts) != 3 or parts[0] != prefix or parts[2] != "no-resolve":
            raise ValueError(f"line {lineno}: expected {prefix},CIDR,no-resolve")
        try:
            network = ipaddress.ip_network(parts[1], strict=True)
        except ValueError as error:
            raise ValueError(f"line {lineno}: invalid CIDR: {parts[1]}") from error
        if network.version != version or "%" in parts[1] or str(network) != parts[1]:
            raise ValueError(f"line {lineno}: expected canonical IPv{version} CIDR")
        networks.append(network)
    if not networks:
        raise ValueError("empty IP address set")
    return list(ipaddress.collapse_addresses(networks))


def subtract_networks(networks, exclusions):
    """Exact set difference over sorted disjoint CIDRs, without enumerating IPs."""
    result = []
    index = 0
    for network in networks:
        cursor, end = int(network.network_address), int(network.broadcast_address)
        address_type = type(network.network_address)
        while index < len(exclusions) and int(exclusions[index].broadcast_address) < cursor:
            index += 1
        while index < len(exclusions) and int(exclusions[index].network_address) <= end:
            excluded = exclusions[index]
            start = int(excluded.network_address)
            if start > cursor:
                result.extend(ipaddress.summarize_address_range(address_type(cursor), address_type(start - 1)))
            cursor = max(cursor, int(excluded.broadcast_address) + 1)
            if cursor > end:
                break
            index += 1
        if cursor <= end:
            result.extend(ipaddress.summarize_address_range(address_type(cursor), address_type(end)))
    return result


def render_ip_rules(head_text, networks, version):
    # Retain the published header; all active rules keep their type and modifier.
    header = []
    for line in head_text.splitlines():
        if is_effective_rule(line):
            break
        header.append(line)
    prefix = "IP-CIDR6" if version == 6 else "IP-CIDR"
    return "\n".join(header + [f"{prefix},{network},no-resolve" for network in networks]) + "\n"


def review_ip_target(rel_path, version):
    """Plan an equivalent baseline compaction; quarantine every new address."""
    path = REPO_ROOT / rel_path
    if path.is_symlink() or not path.is_file():
        return [f"{rel_path}: missing or non-regular generated rule file"], None, None
    head_text = read_head_text(rel_path)
    if head_text is None:
        return [f"{rel_path}: missing published HEAD baseline; manual review required"], None, None
    try:
        text = path.read_text(encoding="utf-8")
        previous = parse_ip_rules(head_text, version)
        candidate = parse_ip_rules(text, version)
    except (OSError, UnicodeError, ValueError) as error:
        return [f"{rel_path}: {error}"], None, None
    missing = subtract_networks(previous, candidate)
    added = subtract_networks(candidate, previous)
    report = {
        "path": rel_path,
        "ip_version": version,
        "status": "rejected_missing_coverage" if missing else "held_for_review" if added else "equivalent",
        "baseline_sha256": hashlib.sha256(head_text.encode("utf-8")).hexdigest(),
        "candidate_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "published_rule_count": count_effective_rules(head_text),
        "candidate_rule_count": count_effective_rules(text),
        "retained_rule_count": len(previous),
        # Decimal strings preserve full IPv6 precision in JSON consumers.
        "retained_address_count": str(sum(network.num_addresses for network in previous)),
        "added_address_count": str(sum(network.num_addresses for network in added)),
        "missing_address_count": str(sum(network.num_addresses for network in missing)),
        "pending_additions": [str(network) for network in added],
        "missing_coverage": [str(network) for network in missing],
    }
    log(f"{rel_path}: {report['candidate_rule_count']} candidate rule(s); "
        f"retaining {report['retained_address_count']} published address(es) in {len(previous)} CIDR(s)")
    for label, networks in (("pending additions", added), ("missing coverage", missing)):
        if networks:
            log(f"{rel_path}: {label}: {len(networks)} CIDR(s), "
                f"{sum(network.num_addresses for network in networks)} address(es)")
            for network in networks[:MAX_REVIEW_LOG_NETWORKS]:
                log(f"  {network}")
            if len(networks) > MAX_REVIEW_LOG_NETWORKS:
                log("  Full CIDR difference is in the IP review report and Actions step summary.")
    if missing:
        return [f"{rel_path}: upstream lost published address coverage; manual review required"], None, report
    return [], render_ip_rules(head_text, previous, version), report


def write_ip_review_report(path, reports, errors):
    if path.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise ValueError("IP review report must be outside the repository")
    payload = json.dumps({"ip_reviews": reports, "errors": errors}, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    log(f"Full IP review report: {path}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        # Keep the full review visible after the runner disappears. Oversized
        # reports stop publication instead of silently dropping review evidence.
        if len(payload.encode("utf-8")) > MAX_REVIEW_SUMMARY_BYTES:
            raise ValueError("IP review report exceeds Actions summary limit; manual review required")
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## China IP coverage review\n\n"
                          "Policy: preserve published coverage and require review of new addresses. "
                          "Missing coverage or validation errors block this sync.\n\n"
                          "```json\n" + payload + "```\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate sync output and preserve published China IP coverage.")
    parser.add_argument("--ip-review-report", type=pathlib.Path,
                        default=pathlib.Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) /
                        "acl4ssr-ip-review.json")
    args = parser.parse_args(argv)
    errors, replacements, reports = [], {}, []
    for rel_path, min_rules in TARGETS.items():
        if rel_path in IP_TARGETS:
            issues, replacement, report = review_ip_target(rel_path, IP_TARGETS[rel_path])
            errors.extend(issues)
            if replacement is not None:
                replacements[rel_path] = replacement
            if report is not None:
                reports.append(report)
        else:
            errors.extend(validate_target(rel_path, min_rules))

    try:
        write_ip_review_report(args.ip_review_report, reports, errors)
    except (OSError, ValueError) as error:
        errors.append(f"IP review report: {error}")
    if errors:
        for error in errors:
            fail(error)
        fail(f"Sync guard failed with {len(errors)} issue(s)")
        sys.exit(1)

    # Only rewrite active IP files after every IP and domain guard has passed.
    for rel_path, replacement in replacements.items():
        (REPO_ROOT / rel_path).write_text(replacement, encoding="utf-8")
    log("Sync guard completed successfully!")


if __name__ == "__main__":
    main()

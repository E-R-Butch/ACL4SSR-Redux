"""Split the ad/privacy block sources into balanced Mihomo rule-provider files.

The block universe is the union of the curated reject lists and the two merged
outputs. Because every rule in it lands in one of two action classes - REJECT
(`🛑 广告拦截`) or REJECT-DROP (`🔒 隐私保护`) - rules inside one uninterrupted
class stage can be rebalanced when they cannot trigger DNS resolution:

* a global dedupe: a rule is dropped when an earlier, higher priority rule
  already covers it (exact duplicate, parent domain suffix, matching keyword,
  or a containing CIDR with the same `no-resolve` flag). No-resolve IP coverage
  is reset at the first resolving rule: an earlier unresolved miss does not
  cover the same rule after DNS has populated the destination address.
* a rebalanced split: each contiguous source stage is partitioned by a digest
  of the rule text into comparable chunks. Membership stays stable when the
  bucket count is unchanged and no overflow rebalancing is required. Stages
  containing resolving IP rules instead use balanced contiguous chunks that
  retain source order, including the position of the DNS-resolution attempt.

Sources are read AND emitted in client reference order: curated privacy lists,
then the merged ad list, then the merged privacy list. Combining the two privacy
stages would move overlapping rules across a different action. Small stages
therefore remain separate even when they cannot fill a provider file.
"""

import argparse
import hashlib
import ipaddress
import json
import pathlib
import re
import sys
from collections import Counter
from itertools import groupby

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

RULESET_PATTERN = re.compile(
    r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?|DST-PORT|IP-CIDR(?:6)?|PROCESS-NAME|URL-REGEX|USER-AGENT|GEOIP|MATCH),"
)

FAMILIES = {
    "adblock": {"group": "🛑 广告拦截", "action": "REJECT"},
    "privacy": {"group": "🔒 隐私保护", "action": "REJECT-DROP"},
}

# (family, source) in client reference order; earlier entries win the dedupe.
SOURCES = (
    ("privacy", "Rules/Core/CustomReject.list"),
    ("privacy", "Rules/Ruleset/Active/HardwareReject.list"),
    ("privacy", "Rules/Ruleset/Active/AdobeReject.list"),
    ("adblock", "Rules/Outputs/MergedADBan.list"),
    ("privacy", "Rules/Outputs/MergedPrivacy.list"),
)

DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX"}
NETWORK_TYPES = {"IP-CIDR", "IP-CIDR6"}
IP_TYPES = NETWORK_TYPES | {"GEOIP"}
DEFAULT_PREFIX = "acl4ssr-adprivacy"
DEFAULT_MAX_RULES = 10000


def log(message):
    print(f"[*] {message}", flush=True)


def parse_rule(line, source):
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 2 or not parts[1]:
        raise ValueError(f"{source}: malformed rule: {line}")
    rule_type = parts[0].upper()
    if not RULESET_PATTERN.match(line):
        raise ValueError(f"{source}: unsupported rule for classical provider: {line}")
    return {
        "line": line,
        "type": rule_type,
        "value": parts[1].lower().rstrip("."),
        "no_resolve": "no-resolve" in (part.lower() for part in parts[2:]),
    }


def read_source(path, family):
    entries = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        rule = parse_rule(line, path.name)
        rule["family"] = family
        entries.append(rule)
    return entries


def exact_key(rule):
    # DNS resolution behavior is part of a network rule's identity, including
    # when its CIDR is identical to an earlier rule.
    modifier = rule["no_resolve"] if rule["type"] in IP_TYPES else None
    return rule["type"], rule["value"], modifier


def may_resolve(rule):
    return rule["type"] in IP_TYPES and not rule["no_resolve"]


def coverage_reason(rule, index):
    key = exact_key(rule)
    if key in index["exact"]:
        return "exact"

    if rule["type"] in DOMAIN_TYPES:
        labels = rule["value"].split(".")
        for start in range(len(labels) - 1):
            ancestor = ".".join(labels[start:])
            if ancestor == rule["value"] and rule["type"] == "DOMAIN-SUFFIX":
                continue
            if ancestor in index["suffix"]:
                return "suffix"
        for keyword in index["keyword"]:
            if keyword in rule["value"]:
                return "keyword"

    if rule["type"] in NETWORK_TYPES:
        try:
            network = ipaddress.ip_network(rule["value"], strict=False)
        except ValueError:
            network = None
        if network is not None:
            for prefix_length in range(network.prefixlen - 1, -1, -1):
                supernet = network.supernet(new_prefix=prefix_length)
                if (supernet.version, str(supernet), rule["no_resolve"]) in index["network"]:
                    return "cidr"

    return None


def register(rule, index):
    rule_type = rule["type"]
    index["exact"].add(exact_key(rule))
    if rule_type == "DOMAIN-SUFFIX":
        index["suffix"].add(rule["value"])
    elif rule_type == "DOMAIN-KEYWORD":
        index["keyword"].add(rule["value"])
    elif rule_type in NETWORK_TYPES:
        try:
            network = ipaddress.ip_network(rule["value"], strict=False)
        except ValueError:
            return
        index["network"].add((network.version, str(network), rule["no_resolve"]))


def dedupe(entries):
    """Drop prior coverage only when it was evaluated in the same DNS state."""
    index = {"exact": set(), "suffix": set(), "keyword": set(), "network": set()}
    kept = []
    reasons = Counter()
    resolution_started = False
    for rule in entries:
        if may_resolve(rule) and not resolution_started:
            # Mihomo attempts DNS once, even on failure. No-resolve IP rules
            # before this boundary may have missed solely because DstIP was
            # empty, so they cannot cover rules after this first attempt.
            index["exact"] = {key for key in index["exact"]
                              if not (key[0] in IP_TYPES and key[2])}
            index["network"] = {key for key in index["network"] if not key[2]}
            resolution_started = True
        reason = coverage_reason(rule, index)
        if reason:
            reasons[reason] += 1
            continue
        kept.append(rule)
        register(rule, index)
    return kept, reasons


def rule_digest(rule):
    return int.from_bytes(hashlib.blake2b(rule["line"].encode("utf-8"), digest_size=8).digest(), "big")


def bucket_count(total, max_rules):
    if max_rules <= 0:
        raise ValueError("max_rules must be a positive integer")
    return max(1, -(-total // max_rules))


def rebalance_buckets(chunks, max_rules):
    """Move the digest-highest rules from oversized buckets to the smallest ones.

    Digest bucketing keeps membership stable but its sizes scatter a little. The
    mean is at most max_rules, so shifting the overflow converges quickly and
    keeps every file within the stated limit.
    """
    while True:
        sizes = [len(chunk) for chunk in chunks]
        largest = max(range(len(chunks)), key=lambda index: (sizes[index], -index))
        smallest = min(range(len(chunks)), key=lambda index: (sizes[index], index))
        if sizes[largest] <= max_rules or sizes[largest] <= sizes[smallest]:
            return chunks
        chunks[smallest].append(chunks[largest].pop())
        chunks[smallest].sort(key=lambda rule: (rule_digest(rule), rule["line"]))


def partition(entries, max_rules):
    """Split one stage, retaining source order if it can trigger DNS."""
    buckets = bucket_count(len(entries), max_rules)
    if any(may_resolve(rule) for rule in entries):
        size, extra = divmod(len(entries), buckets)
        chunks = []
        start = 0
        for index in range(buckets):
            end = start + size + (index < extra)
            chunks.append(entries[start:end])
            start = end
        return chunks
    chunks = [[] for _ in range(buckets)]
    for rule in entries:
        chunks[rule_digest(rule) % buckets].append(rule)
    rebalance_buckets(chunks, max_rules)
    for chunk in chunks:
        chunk.sort(key=lambda rule: (rule["type"], rule["value"], rule["line"]))
    return [chunk for chunk in chunks if chunk]


def render_provider(rules):
    lines = ["payload:"]
    for rule in rules:
        escaped = rule["line"].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  - "{escaped}"')
    return "\n".join(lines) + "\n"


def parse_provider(text):
    payload = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        payload.append(value)
    return payload


def build(max_rules=DEFAULT_MAX_RULES):
    entries = []
    stages = []
    for family, relative in SOURCES:
        if not stages or stages[-1] != family:
            stages.append(family)
        path = REPO_ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing provider source: {relative}")
        source_entries = read_source(path, family)
        for rule in source_entries:
            rule["stage"] = len(stages)
        entries.extend(source_entries)

    kept, reasons = dedupe(entries)

    files = []
    family_file_counts = Counter()
    for stage, stage_rules in groupby(kept, key=lambda rule: rule["stage"]):
        family = stages[stage - 1]
        for chunk in partition(list(stage_rules), max_rules):
            family_file_counts[family] += 1
            index = family_file_counts[family]
            text = render_provider(chunk)
            files.append(
                {
                    "file": f"{DEFAULT_PREFIX}-{family}-{index:02d}.yaml",
                    "family": family,
                    "stage": stage,
                    "group": FAMILIES[family]["group"],
                    "action": FAMILIES[family]["action"],
                    "rules": len(chunk),
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "text": text,
                }
            )
    return files, reasons, len(entries), len(kept)


def manifest(files, reasons, total, kept, max_rules):
    return {
        "note": (
            "Generated by scripts/split_providers.py. Each file maps to the group in "
            "'group'. Preserve the order of ruleset_lines and each payload, including "
            "within stages that can resolve DNS. A family may occur in multiple separated stages."
        ),
        "max_rules_per_file": max_rules,
        "sources": [relative for _, relative in SOURCES],
        "rules": {"parsed": total, "kept": kept, "dropped": total - kept, "reasons": dict(sorted(reasons.items()))},
        "families": FAMILIES,
        "ruleset_lines": [f"RULE-SET,{entry['file'][:-5]},{entry['group']}" for entry in files],
        "files": [{key: value for key, value in entry.items() if key != "text"} for entry in files],
    }


def verify(files, kept, max_rules):
    """Invariants that must hold no matter how the sources change."""
    seen = {}
    resolution_started = False
    for entry in files:
        payload = parse_provider(entry["text"])
        if len(payload) != entry["rules"]:
            raise AssertionError(f"{entry['file']}: manifest count does not match payload")
        if len(payload) > max_rules:
            raise AssertionError(f"{entry['file']}: {len(payload)} rules exceed the {max_rules} limit")
        for line in payload:
            rule = parse_rule(line, entry["file"])
            if may_resolve(rule):
                resolution_started = True
            # One no-resolve rule may be needed on each side of the first DNS
            # attempt. All other duplicate payloads remain an invariant error.
            epoch = resolution_started if rule["type"] in IP_TYPES and rule["no_resolve"] else None
            key = line, epoch
            if key in seen:
                raise AssertionError(f"{line} is repeated in {seen[key]} and {entry['file']}")
            seen[key] = entry["file"]
    if len(seen) != kept:
        raise AssertionError(f"expected {kept} distinct rule evaluations, found {len(seen)}")


def run(out_dir, max_rules, check):
    files, reasons, total, kept = build(max_rules=max_rules)
    verify(files, kept, max_rules)
    manifest_data = manifest(files, reasons, total, kept, max_rules)

    if check:
        differences = 0
        for entry in files:
            path = out_dir / entry["file"]
            if not path.is_file():
                print(f"MISSING: {entry['file']}")
                differences += 1
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                print(f"DIFF: {entry['file']}")
                differences += 1
        manifest_path = out_dir / "providers.manifest.json"
        if not manifest_path.is_file():
            print("MISSING: providers.manifest.json")
            differences += 1
        else:
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                existing_manifest = None
            if existing_manifest != manifest_data:
                print("DIFF: providers.manifest.json")
                differences += 1
        expected = {entry["file"] for entry in files}
        for path in sorted(out_dir.glob("*.yaml")):
            if path.name not in expected:
                print(f"STALE: {path.name}")
                differences += 1
        return differences, manifest_data

    out_dir.mkdir(parents=True, exist_ok=True)
    for entry in files:
        (out_dir / entry["file"]).write_text(entry["text"], encoding="utf-8")
    (out_dir / "providers.manifest.json").write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0, manifest_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="providers", help="Repository-relative output directory.")
    parser.add_argument("--max-rules", type=int, default=DEFAULT_MAX_RULES, help="Maximum rules per file.")
    parser.add_argument("--check", action="store_true", help="Compare with the output directory, write nothing.")
    args = parser.parse_args()

    differences, data = run(REPO_ROOT / args.out_dir, args.max_rules, args.check)
    stats = data["rules"]
    log(
        f"parsed {stats['parsed']} rule(s), kept {stats['kept']}"
        f" (dropped {stats['dropped']}: {stats['reasons'] or 'none'})"
    )
    for entry in data["files"]:
        log(f"{entry['file']}  {entry['rules']:>6} rules  {entry['action']:<11} {entry['group']}")
    if differences:
        warn = f"provider directory is out of date ({differences} difference(s))"
        print(f"[!] {warn}", flush=True)
        sys.exit(1)
    if args.check:
        log("provider directory matches the sources")


if __name__ == "__main__":
    main()

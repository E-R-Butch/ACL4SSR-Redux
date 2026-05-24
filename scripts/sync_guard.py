import pathlib
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
    "Rules/Ruleset/Active/China/ChinaIp.list": 1000,
    "Rules/Ruleset/Active/China/ChinaIpV6.list": 100,
}

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
    if not path.exists():
        return [f"{rel_path}: missing generated rule file"]

    text = path.read_text(encoding="utf-8", errors="replace")
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


def main():
    errors = []
    for rel_path, min_rules in TARGETS.items():
        errors.extend(validate_target(rel_path, min_rules))

    if errors:
        for error in errors:
            fail(error)
        fail(f"Sync guard failed with {len(errors)} issue(s)")
        sys.exit(1)

    log("Sync guard completed successfully!")


if __name__ == "__main__":
    main()

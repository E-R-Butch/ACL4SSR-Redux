import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LIST_DIRS = [
    REPO_ROOT / "Rules/Core",
    REPO_ROOT / "Rules/Outputs",
    REPO_ROOT / "Rules/Ruleset/Active",
]

BLOCKED_RULES = {
    "DOMAIN,disabled.invalid,REJECT",
}


def log(message):
    print(f"[*] {message}", flush=True)


def iter_list_files():
    for list_dir in LIST_DIRS:
        if not list_dir.exists():
            continue
        yield from sorted(list_dir.rglob("*.list"))


def is_effective_rule(line):
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("#"))


def dedupe_lines(lines):
    seen_rules = set()
    output_lines = []
    removed = 0

    for line in lines:
        key = line.strip()
        if is_effective_rule(line):
            if key in BLOCKED_RULES:
                removed += 1
                continue
            if key in seen_rules:
                removed += 1
                continue
            seen_rules.add(key)
        output_lines.append(line)

    return output_lines, removed


def process_file(path, check=False):
    original_text = path.read_text(encoding="utf-8")
    had_final_newline = original_text.endswith("\n")
    lines = original_text.splitlines()

    deduped_lines, removed = dedupe_lines(lines)
    if removed == 0:
        return 0

    rel_path = path.relative_to(REPO_ROOT)
    log(f"{rel_path}: removed {removed} duplicate rule(s)")

    if not check:
        new_text = "\n".join(deduped_lines)
        if had_final_newline:
            new_text += "\n"
        path.write_text(new_text, encoding="utf-8")

    return removed


def main():
    parser = argparse.ArgumentParser(description="Remove duplicate effective rules from .list files.")
    parser.add_argument("--check", action="store_true", help="Report duplicates without modifying files.")
    args = parser.parse_args()

    total_removed = 0
    for path in iter_list_files():
        total_removed += process_file(path, check=args.check)

    if total_removed:
        log(f"Found {total_removed} duplicate rule(s) across list files.")
        if args.check:
            sys.exit(1)
    else:
        log("No duplicate rules found.")


if __name__ == "__main__":
    main()

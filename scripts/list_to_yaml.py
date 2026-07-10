"""Convert Clash .list files to generic Mihomo rule-provider YAML files."""

import argparse
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ("Rules/Outputs", "Rules/Core")
SOURCE_ONLY_FILES = {"ProxyManual.list"}
RULESET_PATTERN = re.compile(
    r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?|DST-PORT|IP-CIDR(?:6)?|PROCESS-NAME|URL-REGEX|USER-AGENT|GEOIP|MATCH),"
)


def read_rules(path):
    rules = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not RULESET_PATTERN.match(line):
            raise ValueError(f"{path}: unsupported rule for classical provider: {line}")
        rules.append(line)
    return rules


def render_provider(rules):
    lines = ["payload:"]
    for rule in rules:
        escaped = rule.replace("\\", "\\\\").replace('"', '\\"')
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


def iter_source_files(source_dirs):
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        yield from (path for path in sorted(source_dir.glob("*.list")) if path.name not in SOURCE_ONLY_FILES)


def display_path(path):
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def run(source_dirs, output_dir, check=False):
    differences = 0
    for source in iter_source_files(source_dirs):
        destination = output_dir / source.with_suffix(".yaml").name
        rules = read_rules(source)

        if check:
            if not destination.is_file():
                print(f"MISSING: {display_path(destination)}")
                differences += 1
                continue
            existing = parse_provider(destination.read_text(encoding="utf-8"))
            if existing != rules:
                print(f"DIFF: {source.name}")
                differences += 1
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_provider(rules), encoding="utf-8")
        print(f"{source.name} -> {display_path(destination)} ({len(rules)} rules)")

    return differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Repository-relative source directory; repeat for multiple directories.",
    )
    parser.add_argument("--output-dir", default="providers")
    parser.add_argument("--check", action="store_true", help="Compare only; never create or modify files.")
    args = parser.parse_args()

    source_dirs = [REPO_ROOT / source for source in (args.sources or DEFAULT_SOURCES)]
    differences = run(source_dirs, REPO_ROOT / args.output_dir, check=args.check)
    if differences:
        sys.exit(1)


if __name__ == "__main__":
    main()

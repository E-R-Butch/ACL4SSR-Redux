import argparse
from datetime import datetime, timezone
import pathlib
import re
import shutil
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTEXT_FILE = REPO_ROOT / "Config/DynamicRegionContext.j2"
GROUPS_FILE = REPO_ROOT / "Config/DynamicProxyGroups.yml.j2"


def replace_dynamic_groups(template_text, context_text, groups_text):
    context_start = template_text.find("{% set all_proxies")
    mixed_port = re.search(r"(?m)^mixed-port:", template_text)
    if context_start < 0 or mixed_port is None or context_start > mixed_port.start():
        raise ValueError("template does not contain a replaceable dynamic context block")

    updated = (
        template_text[:context_start]
        + context_text.rstrip()
        + "\n\n"
        + template_text[mixed_port.start():]
    )

    groups_start = re.search(r"(?m)^proxy-groups:", updated)
    groups_end = re.search(r"(?m)^(?:rule-providers|rules):", updated)
    if groups_start is None or groups_end is None or groups_start.start() > groups_end.start():
        raise ValueError("template does not contain a replaceable proxy-groups block")

    return (
        updated[:groups_start.start()]
        + groups_text.rstrip()
        + "\n"
        + updated[groups_end.start():]
    )


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(
        description="Apply the repository's dynamic region context and proxy groups to a Jinja-enabled Clash template."
    )
    parser.add_argument("template", type=pathlib.Path)
    parser.add_argument(
        "output",
        nargs="?",
        type=pathlib.Path,
        help="Output path. Defaults to replacing the input atomically.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a timestamped backup when replacing the input file.",
    )
    args = parser.parse_args()

    source = args.template
    destination = args.output or source
    original = source.read_text(encoding="utf-8")
    updated = replace_dynamic_groups(
        original,
        CONTEXT_FILE.read_text(encoding="utf-8"),
        GROUPS_FILE.read_text(encoding="utf-8"),
    )

    if args.backup and destination.resolve() == source.resolve():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup = source.with_name(f"{source.name}.bak-{stamp}-dynamic-groups")
        shutil.copy2(source, backup)
        print(f"backup: {backup}")

    atomic_write(destination, updated)
    print(f"updated: {destination}")


if __name__ == "__main__":
    main()

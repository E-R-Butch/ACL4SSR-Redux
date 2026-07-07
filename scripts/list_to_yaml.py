"""Convert .list rule files to Clash rule-provider YAML format."""
import os, sys, re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROVIDERS_DIR = os.path.join(BASE_DIR, "providers")
CHECK_MODE = "--check" in sys.argv

RULESET_PATTERN = re.compile(
    r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?|IP-CIDR(?:6)?|PROCESS-NAME|GEOIP|MATCH),"
)

os.makedirs(PROVIDERS_DIR, exist_ok=True)

sources = [
    ("Rules/Outputs", PROVIDERS_DIR),
    ("Rules/Core", PROVIDERS_DIR),
]

all_files_ok = True
for src_dir, dst_dir in sources:
    src_path = os.path.join(BASE_DIR, src_dir)
    if not os.path.isdir(src_path):
        continue
    os.makedirs(dst_dir, exist_ok=True)
    for fname in sorted(os.listdir(src_path)):
        if not fname.endswith(".list"):
            continue
        src = os.path.join(src_path, fname)
        dst = os.path.join(dst_dir, fname.replace(".list", ".yaml"))

        with open(src, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        bad = [l for l in lines if not RULESET_PATTERN.match(l)]
        if bad:
            print(f"  WARNING: {fname} has {len(bad)} malformed rules: {bad[:3]}...")
            lines = [l for l in lines if RULESET_PATTERN.match(l)]

        if CHECK_MODE:
            if os.path.exists(dst):
                with open(dst, encoding="utf-8") as f:
                    old_payload = set(
                        l.strip().strip('"').strip('- ')
                        for l in f if l.strip().startswith("-")
                    )
                new_payload = set(lines)
                added = new_payload - old_payload
                removed = old_payload - new_payload
                if added or removed:
                    print(f"  DIFF {fname}: +{len(added)} -{len(removed)}")
                    all_files_ok = False
            else:
                print(f"  MISSING: {dst}")
                all_files_ok = False
            continue

        with open(dst, "w", encoding="utf-8") as f:
            f.write("payload:\n")
            for rule in lines:
                escaped = rule.replace("\\", "\\\\").replace('"', '\\"')
                f.write(f'  - "{escaped}"\n')
            f.write("\n")

        print(f"  {fname} -> {os.path.relpath(dst, BASE_DIR)} ({len(lines)} rules)")

if CHECK_MODE and not all_files_ok:
    sys.exit(1)

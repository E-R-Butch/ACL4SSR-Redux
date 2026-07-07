"""Generate split rule-provider YAMLs for Marzban Clash template.
Produces: acl4ssr-adprivacy-privacy-01..05.yaml and adblock-01.yaml
from the ACL4SSR rule list files.
"""
import os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "providers")

os.makedirs(OUT_DIR, exist_ok=True)

def list_to_payload(src_rel):
    """Read .list file and return payload YAML lines."""
    path = os.path.join(BASE_DIR, src_rel)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        rules = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    lines = ["payload:"]
    for rule in rules:
        escaped = rule.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  - "{escaped}"')
    return lines

def write_provider(name, lines):
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  {name} ({len(lines)-1} rules)")

# Privacy-01: CustomReject rules
write_provider("acl4ssr-adprivacy-privacy-01.yaml",
    list_to_payload("Rules/Core/CustomReject.list"))

# Privacy-02: HardwareReject (may have been deleted by codex merge)
hw = list_to_payload("Rules/Ruleset/Active/HardwareReject.list")
write_provider("acl4ssr-adprivacy-privacy-02.yaml",
    hw if hw else ["payload:"])

# Privacy-03: AdobeReject rules
write_provider("acl4ssr-adprivacy-privacy-03.yaml",
    list_to_payload("Rules/Ruleset/Active/AdobeReject.list"))

# Privacy-04: MergedPrivacy (the big one)
write_provider("acl4ssr-adprivacy-privacy-04.yaml",
    list_to_payload("Rules/Outputs/MergedPrivacy.list"))

# Privacy-05: small additional rules
extra = [
    "DOMAIN,apple.comscoreresearch.com",
    "DOMAIN-SUFFIX,crashlytics.com",
    "DOMAIN-SUFFIX,posthog.com",
]
lines = ["payload:"] + [f'  - "{r}"' for r in extra]
write_provider("acl4ssr-adprivacy-privacy-05.yaml", lines)

# AdBlock-01: MergedADBan (the biggest one)
write_provider("acl4ssr-adprivacy-adblock-01.yaml",
    list_to_payload("Rules/Outputs/MergedADBan.list"))

print("\nDone.")

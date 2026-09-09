import ipaddress
import pathlib
import re
import sys
from urllib.parse import urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by CI setup failure instead
    yaml = None


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_FILE = REPO_ROOT / "Config/ACL4SSR_Online_Full.ini"
BASE_CONFIG_FILE = REPO_ROOT / "Config/GeneralConfig.yml"
LIST_DIRS = [
    REPO_ROOT / "Rules/Core",
    REPO_ROOT / "Rules/Outputs",
    REPO_ROOT / "Rules/Ruleset/Active",
    REPO_ROOT / "Rules/Ruleset/Inactive",
]

ALLOWED_SPECIAL_GROUPS = {"DIRECT", "REJECT", "REJECT-DROP"}
REGION_GROUPS = {
    "🇩🇪 德国节点",
    "🇭🇰 香港节点",
    "🇯🇵 日本节点",
    "🇺🇸 美国节点",
    "🇨🇳 台湾节点",
    "🇸🇬 狮城节点",
    "🇰🇷 韩国节点",
}
REGION_FALLBACK = "[]REJECT"
ALLOWED_RULE_TOKENS = {
    "DOMAIN",
    "DOMAIN-KEYWORD",
    "DOMAIN-SUFFIX",
    "DST-PORT",
    "IP-CIDR",
    "IP-CIDR6",
    "PROCESS-NAME",
    "URL-REGEX",
    "USER-AGENT",
}
REPO_RAW_PREFIX = "/E-R-Butch/ACL4SSR-Redux/master/"
BLOCKED_RULES = {"DOMAIN,disabled.invalid,REJECT"}
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)
PRIVATE_ALLOWED_FILES = {pathlib.Path("Rules/Core/LocalAreaNetwork.list")}


def log(message):
    print(f"[*] {message}", flush=True)


def fail(message):
    print(f"[!] {message}", flush=True)


def parse_custom_groups(lines):
    groups = set()
    for line in lines:
        if line.startswith("custom_proxy_group="):
            body = line.split("=", 1)[1]
            group_name = body.split("`", 1)[0].strip()
            if group_name:
                groups.add(group_name)
    return groups


def parse_custom_group_definitions(lines):
    definitions = {}
    for line in lines:
        if not line.startswith("custom_proxy_group="):
            continue
        body = line.split("=", 1)[1]
        group_name = body.split("`", 1)[0].strip()
        if group_name:
            definitions[group_name] = body
    return definitions


def group_selectors(definition):
    """Read the plain-regex/literal selector subset used by this repository."""
    parts = definition.split("`")
    if len(parts) < 3:
        raise ValueError("group is missing its type or selectors")
    if parts[1] == "select":
        return parts[2:]
    if parts[1] in {"url-test", "fallback", "load-balance"}:
        if len(parts) < 5:
            raise ValueError("health-check group is missing selectors, URL or interval")
        return parts[2:-2]
    raise ValueError(f"unsupported group type '{parts[1]}'")


def validate_proxy_only_groups(definitions, root="🎭 Claude"):
    errors = []
    pending = [(root, [root])]
    visited = set()
    while pending:
        name, chain = pending.pop()
        if name == "DIRECT":
            errors.append("proxy-only group reaches DIRECT: " + " -> ".join(chain))
            continue
        if name in visited or name in {"REJECT", "REJECT-DROP"}:
            continue
        visited.add(name)
        if name not in definitions:
            errors.append(f"proxy-only group references missing '{name}'")
            continue
        try:
            selectors = group_selectors(definitions[name])
        except ValueError as error:
            errors.append(f"{name}: {error}")
            continue
        references = [value[2:] for value in selectors if value.startswith("[]")]
        # Subconverter inserts DIRECT if a regex-only group matches no nodes.
        if not references:
            errors.append(f"proxy-only group '{name}' can fall back to DIRECT when no nodes match")
        pending.extend((ref, chain + [ref]) for ref in references)
    return errors


def validate_onedrive_precedence(lines):
    positions = {}
    for index, line in enumerate(lines):
        if line.startswith("surge_ruleset="):
            source = line.split(",", 1)[-1].strip()
            positions.setdefault(urlparse(source).path.rsplit("/", 1)[-1], index)
    one = positions.get("OneDrive.list")
    microsoft = positions.get("MicrosoftDirect.list")
    if one is None or microsoft is None or one >= microsoft:
        return ["OneDrive.list must precede MicrosoftDirect.list so the dedicated group wins"]
    return []


def local_path_from_raw_url(value):
    parsed = urlparse(value)
    if parsed.netloc != "raw.githubusercontent.com" or not parsed.path.startswith(REPO_RAW_PREFIX):
        return None
    return REPO_ROOT / parsed.path.removeprefix(REPO_RAW_PREFIX)


def validate_ini(config_path):
    errors = []
    lines = config_path.read_text(encoding="utf-8").splitlines()
    groups = parse_custom_groups(lines)
    definitions = parse_custom_group_definitions(lines)
    errors.extend(validate_proxy_only_groups(definitions))
    errors.extend(validate_onedrive_precedence(lines))

    for group_name in sorted(REGION_GROUPS):
        definition = definitions.get(group_name)
        if definition is None:
            errors.append(f"{config_path} missing required region group '{group_name}'")
        else:
            try:
                selectors = group_selectors(definition)
                references = [value for value in selectors if value.startswith("[]")]
                if references != [REGION_FALLBACK]:
                    errors.append(
                        f"{config_path} region group '{group_name}' must use only {REGION_FALLBACK} "
                        "as a literal member; global groups break region isolation"
                    )
                if not any(not value.startswith("[]") for value in selectors):
                    errors.append(f"{config_path} region group '{group_name}' has no node filter")
            except ValueError as error:
                errors.append(f"{config_path} region group '{group_name}': {error}")

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue

        if stripped.startswith("surge_ruleset="):
            body = stripped.split("=", 1)[1]
            target, _, source = body.partition(",")
            target = target.strip()
            if target not in groups:
                errors.append(f"{config_path}:{lineno} ruleset target '{target}' has no matching group")
            local_path = local_path_from_raw_url(source.strip())
            if local_path is not None and not local_path.is_file():
                errors.append(f"{config_path}:{lineno} references missing repository file '{local_path}'")

        if stripped.startswith("clash_rule_base="):
            source = stripped.split("=", 1)[1].strip()
            local_path = local_path_from_raw_url(source)
            if local_path is not None and not local_path.is_file():
                errors.append(f"{config_path}:{lineno} references missing base config '{local_path}'")

        if stripped.startswith("custom_proxy_group="):
            body = stripped.split("=", 1)[1]
            group_name, separator, definition = body.partition("`")
            if not group_name or not separator:
                errors.append(f"{config_path}:{lineno} malformed custom_proxy_group")
                continue
            if "``" in definition or definition.endswith("`"):
                errors.append(f"{config_path}:{lineno} group '{group_name}' contains an empty segment")

            try:
                selectors = group_selectors(body)
            except ValueError as error:
                errors.append(f"{config_path}:{lineno} group '{group_name}': {error}")
                continue
            for selector in selectors:
                if selector.startswith("[]"):
                    ref = selector[2:]
                    if ref not in ALLOWED_SPECIAL_GROUPS and ref not in groups:
                        errors.append(f"{config_path}:{lineno} group '{group_name}' references undefined '{ref}'")
                else:
                    try:
                        re.compile(selector)
                    except re.error as error:
                        errors.append(f"{config_path}:{lineno} group '{group_name}' invalid regex: {error}")
    return errors


def parse_network(token, payload):
    expected_version = 6 if token == "IP-CIDR6" else 4
    network = ipaddress.ip_network(payload, strict=True)
    if network.version != expected_version:
        raise ValueError(f"{token} contains IPv{network.version} network")
    return network


def is_forbidden_private_network(network):
    return any(network.version == private.version and network.subnet_of(private) for private in PRIVATE_NETWORKS)


def validate_list_file(path):
    errors = []
    non_comment_rules = 0
    relative_path = path.relative_to(REPO_ROOT)

    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        non_comment_rules += 1

        if line in BLOCKED_RULES:
            errors.append(f"{path}:{lineno} blocked placeholder rule '{line}'")
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[1]:
            errors.append(f"{path}:{lineno} missing comma-separated rule payload")
            continue

        token, payload = parts[:2]
        if token not in ALLOWED_RULE_TOKENS:
            errors.append(f"{path}:{lineno} unsupported rule token '{token}'")
            continue

        if token in {"IP-CIDR", "IP-CIDR6"}:
            if len(parts) > 3 or (len(parts) == 3 and parts[2] != "no-resolve"):
                errors.append(f"{path}:{lineno} unsupported CIDR modifier")
            try:
                network = parse_network(token, payload)
                if relative_path not in PRIVATE_ALLOWED_FILES and is_forbidden_private_network(network):
                    errors.append(f"{path}:{lineno} private/local network outside LocalAreaNetwork.list")
            except ValueError as error:
                errors.append(f"{path}:{lineno} invalid canonical network '{payload}': {error}")
        elif token == "DST-PORT":
            try:
                port = int(payload)
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}:{lineno} invalid destination port '{payload}'")
        elif len(parts) != 2:
            errors.append(f"{path}:{lineno} unexpected extra rule fields")

    if non_comment_rules == 0:
        errors.append(f"{path} contains no effective rules")
    return errors


def validate_yaml(path):
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        errors = []
        top_level_keys = set()
        for lineno, raw_line in enumerate(text.splitlines(), start=1):
            if "\t" in raw_line:
                errors.append(f"{path}:{lineno} YAML indentation must not contain tabs")
            line = raw_line.split("#", 1)[0].rstrip()
            if not line or line.startswith(" "):
                continue
            match = re.match(r"^([A-Za-z0-9_-]+):(?:\s|$)", line)
            if not match:
                errors.append(f"{path}:{lineno} invalid top-level YAML entry")
                continue
            key = match.group(1)
            if key in top_level_keys:
                errors.append(f"{path}:{lineno} duplicate top-level YAML key '{key}'")
            top_level_keys.add(key)
        required = {"mixed-port", "allow-lan", "dns"}
        errors.extend(f"{path} missing required key '{key}'" for key in sorted(required - top_level_keys))
        return errors
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return [f"{path} invalid YAML: {error}"]
    if not isinstance(parsed, dict):
        return [f"{path} must contain a YAML mapping"]
    required = {"mixed-port", "allow-lan", "dns"}
    missing = sorted(required - parsed.keys())
    return [f"{path} missing required key '{key}'" for key in missing]


def collect_errors():
    errors = []
    log(f"Validating config: {CONFIG_FILE}")
    errors.extend(validate_ini(CONFIG_FILE))
    errors.extend(validate_yaml(BASE_CONFIG_FILE))
    for list_dir in LIST_DIRS:
        if not list_dir.exists():
            continue
        for path in sorted(list_dir.rglob("*.list")):
            log(f"Checking list file: {path.relative_to(REPO_ROOT)}")
            errors.extend(validate_list_file(path))
    return errors


def main():
    errors = collect_errors()
    if errors:
        for error in errors:
            fail(error)
        fail(f"Validation failed with {len(errors)} issue(s)")
        sys.exit(1)
    log("Validation completed successfully!")


if __name__ == "__main__":
    main()

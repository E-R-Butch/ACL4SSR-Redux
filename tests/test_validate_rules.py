import ipaddress
import unittest

from scripts import validate_rules


class ValidateRulesTests(unittest.TestCase):
    def test_region_groups_have_nonempty_fallbacks(self):
        lines = validate_rules.CONFIG_FILE.read_text(encoding="utf-8").splitlines()
        definitions = validate_rules.parse_custom_group_definitions(lines)

        for group_name in validate_rules.REGION_GROUPS:
            self.assertIn(group_name, definitions)
            self.assertIn(validate_rules.REGION_FALLBACK, definitions[group_name])

    def test_rejects_noncanonical_network(self):
        with self.assertRaises(ValueError):
            validate_rules.parse_network("IP-CIDR", "192.0.2.1/24")

    def test_rejects_wrong_ip_family(self):
        with self.assertRaises(ValueError):
            validate_rules.parse_network("IP-CIDR6", "192.0.2.0/24")

    def test_detects_private_network(self):
        self.assertTrue(validate_rules.is_forbidden_private_network(ipaddress.ip_network("172.16.1.0/24")))
        self.assertFalse(validate_rules.is_forbidden_private_network(ipaddress.ip_network("192.0.2.0/24")))


if __name__ == "__main__":
    unittest.main()

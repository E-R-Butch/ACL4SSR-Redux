import ipaddress
import unittest

from scripts import validate_rules


class ValidateRulesTests(unittest.TestCase):
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

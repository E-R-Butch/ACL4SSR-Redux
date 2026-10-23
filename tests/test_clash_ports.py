import unittest

from scripts import fetch_assets


class ClashPortTests(unittest.TestCase):
    def test_valid_ports_are_preserved_and_canonicalized(self):
        self.assertEqual(
            fetch_assets.process_clash_rule_list("DST-PORT,1\nDST-PORT,80\ndst-port, 0443\nDST-PORT,65535\n", "TEST"),
            {"DST-PORT,1", "DST-PORT,80", "DST-PORT,443", "DST-PORT,65535"},
        )

    def test_invalid_ports_are_skipped_without_domain_normalization(self):
        for value in ("0", "65536", "-1", "+443", "443.0", "443.example", "443-444", "443/udp", "", "４４３", "9" * 5000):
            with self.subTest(value=value):
                self.assertEqual(fetch_assets.process_clash_rule_list(f"DST-PORT,{value}", "TEST"), set())

    def test_ports_cannot_import_extra_action_or_modifier(self):
        for line in ("DST-PORT,443,DIRECT", "DST-PORT,443,no-resolve", "DST-PORT,443,"):
            with self.subTest(line=line):
                self.assertEqual(fetch_assets.process_clash_rule_list(line, "TEST"), set())


if __name__ == "__main__":
    unittest.main()

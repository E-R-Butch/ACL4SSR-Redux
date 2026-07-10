import pathlib
import tempfile
import unittest

from scripts import build_rules


class BuildRulesTests(unittest.TestCase):
    def test_domain_suffix_wins_over_exact_domain(self):
        rules = {
            ("DOMAIN", "example.com"),
            ("DOMAIN-SUFFIX", "example.com"),
            ("DOMAIN", "other.example"),
        }
        resolved, conflicts = build_rules.resolve_domain_conflicts(rules)
        self.assertNotIn(("DOMAIN", "example.com"), resolved)
        self.assertIn(("DOMAIN-SUFFIX", "example.com"), resolved)
        self.assertEqual(1, len(conflicts))

    def test_parse_rule_preserves_modifiers(self):
        self.assertEqual(
            ("IP-CIDR", "192.0.2.0/24", "no-resolve"),
            build_rules.parse_rule("IP-CIDR,192.0.2.0/24,no-resolve"),
        )

    def test_build_target_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            ingredients = root / "ingredients"
            ingredients.mkdir()
            (ingredients / "one.list").write_text(
                "DOMAIN,b.example\nDOMAIN-SUFFIX,a.example\n",
                encoding="utf-8",
            )
            output = root / "output.list"
            config = {"inputs": ["one.list"], "output": output, "title": "Test"}
            build_rules.build_target("test", config, ingredients)
            first = output.read_bytes()
            build_rules.build_target("test", config, ingredients)
            self.assertEqual(first, output.read_bytes())


if __name__ == "__main__":
    unittest.main()

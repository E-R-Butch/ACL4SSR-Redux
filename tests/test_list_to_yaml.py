import pathlib
import tempfile
import unittest

from scripts import list_to_yaml


class ListToYamlTests(unittest.TestCase):
    def test_render_parse_round_trip(self):
        rules = ["DOMAIN,example.com", "IP-CIDR,192.0.2.0/24,no-resolve"]
        self.assertEqual(rules, list_to_yaml.parse_provider(list_to_yaml.render_provider(rules)))

    def test_check_mode_does_not_create_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "test.list").write_text("DOMAIN,example.com\n", encoding="utf-8")
            output = root / "providers"
            self.assertEqual(1, list_to_yaml.run([source], output, check=True))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

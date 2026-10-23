import io
import unittest
import warnings
import zipfile
from unittest import mock

from scripts import fetch_assets


def make_archive(*members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members:
            archive.writestr(name, content)
    return buffer.getvalue()


class TrancoValidationTests(unittest.TestCase):
    def test_selects_named_csv_instead_of_first_archive_member(self):
        payload = make_archive(
            ("README.txt", "Tranco ranking"),
            ("top-1m.csv", "1,example.com\r\n2,ads.example.com\r\n3,beyond.example\r\n"),
        )

        self.assertEqual(fetch_assets.read_tranco_registrable(payload, limit=2), {"example.com"})

    def test_rejects_missing_or_ambiguous_csv_member(self):
        invalid_members = (
            (),
            (("error.html", "<html>upstream unavailable</html>"),),
            (("other.csv", "1,example.com\n"),),
            (("nested/top-1m.csv", "1,example.com\n"),),
            (("top-1m.csv/", ""),),
            (("top-1m.csv", "1,example.com\n"), ("top-1m.csv", "1,other.example\n")),
        )
        for members in invalid_members:
            with self.subTest(members=members), warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                payload = make_archive(*members)
                with self.assertRaisesRegex(ValueError, "Tranco.*top-1m.csv"):
                    fetch_assets.read_tranco_registrable(payload, limit=1)

    def test_rejects_non_zip_response(self):
        with self.assertRaisesRegex(ValueError, "Tranco.*ZIP"):
            fetch_assets.read_tranco_registrable(b"<html>error</html>", limit=1)

    def test_rejects_corrupt_csv_member(self):
        payload = make_archive(("top-1m.csv", "1,example.com\n"))
        payload = payload.replace(b"1,example.com", b"1,examplf.com", 1)
        with self.assertRaisesRegex(ValueError, "Tranco.*ZIP"):
            fetch_assets.read_tranco_registrable(payload, limit=1)

    def test_rejects_invalid_utf8_instead_of_replacing_bytes(self):
        payload = make_archive(("top-1m.csv", b"1,example.com\n2,bad\xff.example\n"))
        with self.assertRaisesRegex(ValueError, "Tranco.*UTF-8"):
            fetch_assets.read_tranco_registrable(payload, limit=2)

    def test_rejects_malformed_rows_instead_of_skipping_them(self):
        for row in ("<html>error</html>", "rank,domain", "", "2", "2,other.example,extra"):
            with self.subTest(row=row):
                payload = make_archive(("top-1m.csv", f"1,example.com\n{row}\n3,last.example\n"))
                with self.assertRaisesRegex(ValueError, "Tranco.*(row|rank)"):
                    fetch_assets.read_tranco_registrable(payload, limit=3)

    def test_rejects_non_csv_line_separators(self):
        for separator in ("\v", "\f", "\x1c", "\x85", "\u2028"):
            with self.subTest(separator=separator):
                payload = make_archive(("top-1m.csv", f"1,example.com{separator}2,other.example\n"))
                with self.assertRaisesRegex(ValueError, "Tranco.*row"):
                    fetch_assets.read_tranco_registrable(payload, limit=2)

    def test_rejects_invalid_or_nonconsecutive_ranks(self):
        for rank in ("0", "-2", "+2", "02", " 2", "2 ", "2.0", "２", "1", "3"):
            with self.subTest(rank=rank):
                payload = make_archive(("top-1m.csv", f"1,example.com\n{rank},other.example\n"))
                with self.assertRaisesRegex(ValueError, "Tranco.*rank"):
                    fetch_assets.read_tranco_registrable(payload, limit=2)

    def test_ranking_must_start_at_one(self):
        payload = make_archive(("top-1m.csv", "2,example.com\n"))
        with self.assertRaisesRegex(ValueError, "Tranco.*rank"):
            fetch_assets.read_tranco_registrable(payload, limit=1)

    def test_rejects_invalid_domains_without_normalizing_them_into_hosts(self):
        invalid_domains = (
            "", "localhost", "https://example.com", "example.com/path", "example.com:443",
            ".example.com", "example.com.", " example.com", "example.com ", "exa_mple.com",
            "-example.com", "example-.com", "example..com", "*.example.com", "éxample.com", "K.example",
            "127.0.0.1", "host.123", f"{'x' * 64}.com", ".".join(["x" * 63] * 4),
        )
        for domain in invalid_domains:
            with self.subTest(domain=domain):
                payload = make_archive(("top-1m.csv", f"1,{domain}\n"))
                with self.assertRaisesRegex(ValueError, "Tranco.*domain"):
                    fetch_assets.read_tranco_registrable(payload, limit=1)

    def test_accepts_case_insensitive_ascii_and_punycode_domains(self):
        payload = make_archive(("top-1m.csv", "1,Example.COM\n2,xn--bcher-kva.de\n"))
        self.assertEqual(
            fetch_assets.read_tranco_registrable(payload, limit=2),
            {"example.com", "xn--bcher-kva.de"},
        )

    def test_skips_known_upstream_non_host_format(self):
        # These six non-host entries occur in the otherwise valid live CSV.
        # Preserve their exclusion rather than treating a suffix as popular.
        entries = (
            "_wildcard_.ph", "_wildcard_.com.ph", "_wildcard_.org.ph",
            "_wildcard_.net.ph", "_wildcard_.ws", "_wildcard_.xn--fiqs8s",
        )
        content = "1,example.com\n" + "".join(
            f"{rank},{domain}\n" for rank, domain in enumerate(entries, start=2)
        )
        payload = make_archive(("top-1m.csv", content))
        self.assertEqual(fetch_assets.read_tranco_registrable(payload, limit=7), {"example.com"})

        # New valid suffixes do not require a hardcoded per-domain exception.
        payload = make_archive(("top-1m.csv", "1,example.com\n2,_wildcard_.new.example\n"))
        self.assertEqual(fetch_assets.read_tranco_registrable(payload, limit=2), {"example.com"})

    def test_non_host_exception_still_validates_its_suffix(self):
        for suffix in ("", ".ph", "bad_.ph", "ph/path", "ph:443", "ph ", "127.0.0.1"):
            with self.subTest(suffix=suffix):
                payload = make_archive(("top-1m.csv", f"1,example.com\n2,_wildcard_.{suffix}\n"))
                with self.assertRaisesRegex(ValueError, "Tranco.*domain"):
                    fetch_assets.read_tranco_registrable(payload, limit=2)

    def test_rejects_duplicate_non_host_entries(self):
        payload = make_archive(("top-1m.csv", "1,example.com\n2,_wildcard_.ph\n3,_wildcard_.ph\n"))
        with self.assertRaisesRegex(ValueError, "Tranco.*duplicate domain"):
            fetch_assets.read_tranco_registrable(payload, limit=3)

    def test_non_host_entries_cannot_make_an_empty_protection_set_valid(self):
        payload = make_archive(("top-1m.csv", "1,_wildcard_.ph\n"))
        with self.assertRaisesRegex(ValueError, "Tranco.*no usable domains"):
            fetch_assets.read_tranco_registrable(payload, limit=1)

    def test_rejects_duplicate_hosts_but_not_duplicate_registrable_domains(self):
        payload = make_archive(("top-1m.csv", "1,example.com\n2,EXAMPLE.com\n"))
        with self.assertRaisesRegex(ValueError, "Tranco.*duplicate domain"):
            fetch_assets.read_tranco_registrable(payload, limit=2)

    def test_rejects_empty_and_incomplete_requested_rank_window(self):
        for content in ("", "1,example.com\n"):
            with self.subTest(content=content):
                payload = make_archive(("top-1m.csv", content))
                with self.assertRaisesRegex(ValueError, "Tranco.*incomplete.*2"):
                    fetch_assets.read_tranco_registrable(payload, limit=2)

    def test_production_default_requires_all_one_million_ranks(self):
        payload = make_archive(("top-1m.csv", "1,example.com\n2,other.example\n"))
        with self.assertRaisesRegex(ValueError, "Tranco.*incomplete.*1000000"):
            fetch_assets.read_tranco_registrable(payload)

    def test_rejects_invalid_limits(self):
        payload = make_archive(("top-1m.csv", "1,example.com\n"))
        for limit in (0, -1, 1.5, True):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "limit"):
                fetch_assets.read_tranco_registrable(payload, limit=limit)

    def test_invalid_archive_aborts_main_before_build_or_install(self):
        invalid_payloads = (
            make_archive(("error.html", "<html>temporarily unavailable</html>")),
            make_archive(("top-1m.csv", "1,example.com\n")),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), \
                    mock.patch.object(fetch_assets, "fetch", return_value="irrelevant fixture"), \
                    mock.patch.object(fetch_assets, "fetch_binary", return_value=payload), \
                    mock.patch.object(fetch_assets, "build_outputs") as build, \
                    mock.patch.object(fetch_assets, "install_outputs") as install:
                with self.assertRaisesRegex(ValueError, "Tranco"):
                    fetch_assets.main()
                build.assert_not_called()
                install.assert_not_called()


if __name__ == "__main__":
    unittest.main()

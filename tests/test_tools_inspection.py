import io
import json
import stat
import struct
import unittest
import zipfile
from dataclasses import replace

from agent_ext.contracts import ChallengeScope
from agent_ext.tools.inspection import InspectionError, Limits, inspect, observation_key


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in entries:
            output.writestr(name, data)
    return stream.getvalue()


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.limits = Limits()

    def test_header_identification_does_not_invent_a_type(self):
        for data, kind in ((b"\x7fELFxxx", "elf"), (b"plain", "unknown"), (b"", "unknown")):
            self.assertEqual(inspect(data, "identify", 0, self.limits)["kind"], kind)

    def test_text_hex_offsets_and_binary_replacement(self):
        limits = replace(self.limits, preview_bytes=2)
        result = inspect(b"a\xffbc", "text", 1, limits)
        self.assertEqual(result["text"], "\ufffdb")
        self.assertEqual(result["bytes_inspected"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(inspect(b"a\xffbc", "hex", 1, limits)["hex"], "ff62")

    def test_string_count_lengths_offsets_and_scan_coverage(self):
        limits = replace(self.limits, strings=1, string_bytes=4)
        result = inspect(b"\x00abcdef\x00second", "strings", 0, limits)
        self.assertEqual(result["matches"], [dict(offset=1, text="abcd", shortened=True)])
        self.assertTrue(result["truncated"])
        self.assertFalse(result["scan_complete"])
        self.assertEqual(result["bytes_scanned"], 8)

    def test_no_readable_strings_is_a_complete_bounded_scan(self):
        result = inspect(b"\x00\xff", "strings", 0, self.limits)
        self.assertTrue(result["scan_complete"])
        self.assertEqual(result["matches"], [])

    def test_output_expansion_is_bounded_valid_json(self):
        result = inspect(b"\x01" * 5000, "text", 0,
                         replace(self.limits, preview_bytes=5000, output_bytes=1024))
        self.assertTrue(result["observation_omitted"])
        self.assertLessEqual(len(json.dumps(result).encode()), 1024)

    def test_input_operation_and_offset_validation(self):
        for operation, offset in (("shell", 0), ("text", -1), ("text", True), ("identify", 1)):
            with self.subTest(operation=operation, offset=offset), self.assertRaises(InspectionError):
                inspect(b"abc", operation, offset, self.limits)
        with self.assertRaisesRegex(InspectionError, "input_limit"):
            inspect(b"12345", "identify", 0, replace(self.limits, input_bytes=4))

    def test_zip_listing_never_extracts_and_marks_declared_sizes(self):
        result = inspect(archive([("a.txt", "hello"), ("folder/b", "world")]), "zip_list", 0, self.limits)
        self.assertEqual(result["entries_seen"], 2)
        self.assertEqual(result["declared_expanded_bytes"], 10)
        self.assertFalse(result["extracted"])
        self.assertFalse(result["sizes_verified"])

    def test_archive_traversal_absolute_and_symlink_rejected(self):
        for name in ("../outside", "/absolute", "C:/drive", "a/../../b", "..\\outside"):
            with self.subTest(name=name), self.assertRaisesRegex(InspectionError, "unsafe_archive_path"):
                inspect(archive([(name, "data")]), "zip_list", 0, self.limits)
        member = zipfile.ZipInfo("link")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(InspectionError, "archive_symlink"):
            inspect(archive([(member, "target")]), "zip_list", 0, self.limits)

    def test_archive_entry_and_declared_expansion_limits(self):
        data = archive([("a", "x" * 500), ("b", "y")])
        with self.assertRaisesRegex(InspectionError, "archive_metadata_limit"):
            inspect(data, "zip_list", 0, replace(self.limits, archive_entries=1))
        with self.assertRaisesRegex(InspectionError, "archive_expansion_limit"):
            inspect(data, "zip_list", 0, replace(self.limits, archive_expanded_bytes=100))

    def test_forged_entry_count_and_truncated_zip_are_rejected(self):
        data = bytearray(archive([("a", "x"), ("b", "y")]))
        end = data.rfind(b"PK\x05\x06")
        struct.pack_into("<2H", data, end + 8, 1, 1)
        for malformed in (bytes(data), bytes(data[:-5]), b"random"):
            with self.assertRaises(InspectionError):
                inspect(malformed, "zip_list", 0, self.limits)

    def test_identity_invalidates_bytes_instance_parameters_not_attempt(self):
        scope = ChallengeScope(1, "synthetic", "fixture", "material-1", "attempt-1", "gen-1")
        key = observation_key(scope, "digest-a", "text", 0, self.limits)
        self.assertEqual(key, observation_key(replace(scope, attempt_id="attempt-2"),
                                             "digest-a", "text", 0, self.limits))
        alternatives = [(replace(scope, instance_generation="gen-2"), "digest-a", "text", 0, self.limits),
                        (scope, "digest-b", "text", 0, self.limits),
                        (scope, "digest-a", "hex", 0, self.limits),
                        (scope, "digest-a", "text", 1, self.limits),
                        (scope, "digest-a", "text", 0, replace(self.limits, preview_bytes=2))]
        for args in alternatives:
            self.assertNotEqual(key, observation_key(*args))


if __name__ == "__main__":
    unittest.main()

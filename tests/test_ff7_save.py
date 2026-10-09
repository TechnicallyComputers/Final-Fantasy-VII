"""Synthetic cards only: format, export safety, and optional C/Python parity."""
import ctypes
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ff7_save as save


def synthetic_card():
    base = bytearray((i * 17 + 11) & 255 for i in range(save.CARD_SIZE))
    base[:128] = bytes(128)
    base[:2] = b"MC"
    base[127] = ord("M") ^ ord("C")
    for slot in range(1, 16):
        frame = bytearray(128)
        struct.pack_into("<IIH", frame, 0, 0x51, 8192, 0xFFFF)
        frame[10:17] = b"FF7TEST"
        for byte in frame[:127]:
            frame[127] ^= byte
        base[slot * 128:(slot + 1) * 128] = frame
    return bytes(base)


def sample_party():
    return save.Party((0, 7, 0x100), (save.Member(0x100, 10, 1, bytes(range(132))),))


def repair_crc(data):
    struct.pack_into("<I", data, 60, save.crc(data))


class FormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = synthetic_card()
        cls.slots = {1: sample_party(), 15: save.Party((1, 2, save.EMPTY), ())}
        cls.tail = save.encode_extension(cls.base, cls.slots)

    def test_standard_and_extended_roundtrip(self):
        standard = save.parse_card(self.base)
        self.assertFalse(standard.extended)
        extended = save.parse_card(self.base + self.tail)
        self.assertTrue(extended.extended)
        self.assertEqual(extended.base, self.base)
        self.assertEqual(extended.slots, self.slots)
        self.assertEqual(save.encode_extension(extended.base, extended.slots), self.tail)
        self.assertEqual(self.tail[24:56], hashlib.sha256(self.base).digest())
        self.assertEqual(save.describe(extended)["directory_slots"][0]["active_extra_ids"], [256])

    def test_all_truncations_and_each_corrupt_tail_byte(self):
        for size in range(1, len(self.tail)):
            with self.subTest(truncation=size), self.assertRaises(save.SaveFormatError):
                save.parse_card(self.base + self.tail[:size])
        for offset in range(len(self.tail)):
            tail = bytearray(self.tail)
            tail[offset] ^= 1
            with self.subTest(corruption=offset), self.assertRaises(save.SaveFormatError):
                save.parse_card(self.base + tail)

    def test_whole_card_binding(self):
        base = bytearray(self.base)
        base[-1] ^= 1
        with self.assertRaisesRegex(save.SaveFormatError, "complete base card"):
            save.parse_card(base + self.tail)

    def test_bad_sizes_headers_and_unknown_formats(self):
        for data in (b"", self.base[:-1], b"VgsM" + self.base, self.base + b"x",
                     self.base + bytes(save.MAX_EXTENSION + 1)):
            with self.assertRaises(save.SaveFormatError):
                save.parse_card(data)
        for offset in (0, 127):
            data = bytearray(self.base)
            data[offset] ^= 1
            with self.assertRaises(save.SaveFormatError):
                save.parse_card(data)

    def test_valid_crc_invalid_envelope_fields(self):
        for offset, value in ((8, 2), (10, 63), (12, 0), (16, 16), (18, 1), (20, 1),
                              (56, 1), (64, 0), (65, 1), (68, 255), (288, 1)):
            tail = bytearray(self.tail)
            tail[offset] = value
            repair_crc(tail)
            with self.subTest(offset=offset), self.assertRaises(save.SaveFormatError):
                save.parse_card(self.base + tail)

    def test_valid_crc_invalid_payload_fields(self):
        for offset, value in ((8, 1), (16, 17), (18, 10), (22, 9), (56, 1),
                              (64, 0), (70, 9), (73, 2), (74, 1), (80, 255), (82, 11), (83, 128)):
            tail = bytearray(self.tail)
            payload = bytearray(tail[72:288])
            payload[offset] = value
            if offset == 80:
                payload[81] = 255
            repair_crc(payload)
            tail[72:288] = payload
            repair_crc(tail)
            with self.subTest(offset=offset), self.assertRaises(save.SaveFormatError):
                save.parse_card(self.base + tail)

    def test_stored_party_and_version2_migration(self):
        party = save.Party((0, 7, 256), sample_party().members,
                          (256, 7, save.EMPTY), (255, 10, 255), True)
        digest = hashlib.sha256(self.base).digest()
        payload = save.encode_payload(party, digest)
        self.assertEqual(save.decode_payload(payload, digest), party)
        legacy = bytearray(payload[:64] + payload[80:])
        struct.pack_into('<HHI', legacy, 8, 2, 64, len(legacy))
        repair_crc(legacy)
        migrated = save.decode_payload(legacy, digest)
        self.assertEqual(migrated.active, party.active)
        self.assertFalse(migrated.stored_known)
        self.assertEqual(migrated.stored, (save.EMPTY,) * 3)

    def test_directory_slot_must_be_allocated_first_and_checksum_valid(self):
        for offset in (128, 255):
            base = bytearray(self.base)
            base[offset] ^= 1
            with self.assertRaises(save.SaveFormatError):
                save.encode_extension(base, self.slots)

    def test_maximum_and_empty_envelopes(self):
        members = tuple(save.Member(0x100 + i, 10, 1, bytes(132)) for i in range(16))
        slots = {i: save.Party((save.EMPTY,) * 3, members) for i in range(1, 16)}
        maximum = self.base + save.encode_extension(self.base, slots)
        self.assertEqual(len(maximum), save.MAX_FILE)
        self.assertEqual(save.parse_card(maximum).slots, slots)
        self.assertEqual(save.parse_card(self.base + save.encode_extension(self.base, {})).slots, {})

    def test_invalid_roster_and_duplicate_identity(self):
        member = sample_party().members[0]
        for party in (save.Party((0, 7, 10), (member,)), save.Party((0, 0, 256), (member,)),
                      save.Party((0, 7, 256), (member, member)),
                      save.Party((0, 7, 256), (save.Member(256, 10, 0, bytes(132)),))):
            with self.assertRaises(save.SaveFormatError):
                save.encode_extension(self.base, {1: party})


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "extended.mcd"
        self.output = self.root / "standard.mcd"
        self.base = synthetic_card()
        self.extended = self.base + save.encode_extension(self.base, {1: sample_party()})
        self.source.write_bytes(self.extended)

    def test_export_exact_bytes_and_source_unchanged(self):
        report = save.export_standard(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), self.base)
        self.assertEqual(self.source.read_bytes(), self.extended)
        self.assertEqual(report["directory_slots"][0]["active_extra_ids"], [256])
        second = self.root / "second.mcd"
        save.export_standard(self.output, second)
        self.assertEqual(second.read_bytes(), self.base)

    def test_reject_input_overwrite_existing_output_and_hardlink_alias(self):
        with self.assertRaises(save.SaveFormatError):
            save.export_standard(self.source, self.source)
        self.output.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            save.export_standard(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"keep")
        alias = self.root / "alias.mcd"
        os.link(self.source, alias)
        with self.assertRaises(FileExistsError):
            save.export_standard(self.source, alias)
        self.assertEqual(self.source.read_bytes(), self.extended)

    def test_corruption_creates_no_output(self):
        self.source.write_bytes(self.extended[:-1])
        with self.assertRaises(save.SaveFormatError):
            save.export_standard(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_explicit_recovery_only_allows_stale_base_binding(self):
        stale = bytearray(self.extended)
        stale[save.CARD_SIZE - 1] ^= 1
        self.source.write_bytes(stale)
        with self.assertRaisesRegex(save.SaveFormatError, "complete base card"):
            save.export_standard(self.source, self.output)
        report = save.export_standard(self.source, self.output, recover_base=True)
        self.assertTrue(report["recovered_stale_binding"])
        self.assertEqual(self.output.read_bytes(), stale[:save.CARD_SIZE])
        self.assertEqual(self.source.read_bytes(), stale)
        self.output.unlink()
        for bad in (stale[:-1], stale[:save.CARD_SIZE - 1], stale + b"x"):
            self.source.write_bytes(bad)
            with self.assertRaises(save.SaveFormatError):
                save.export_standard(self.source, self.output, recover_base=True)
            self.assertFalse(self.output.exists())
        bad = bytearray(stale)
        bad[-1] ^= 1  # CRC corruption is never bypassed by recovery.
        self.source.write_bytes(bad)
        with self.assertRaises(save.SaveFormatError):
            save.export_standard(self.source, self.output, recover_base=True)
        self.assertFalse(self.output.exists())

    def test_recovery_cli_reports_metadata_discard(self):
        stale = bytearray(self.extended)
        stale[save.CARD_SIZE - 1] ^= 1
        self.source.write_bytes(stale)
        result = subprocess.run([sys.executable, str(ROOT / "tools/ff7_save.py"),
                                 "export-standard", str(self.source), "--output", str(self.output),
                                 "--recover-base"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"recovered_stale_binding": true', result.stdout)
        self.assertEqual(self.output.read_bytes(), stale[:save.CARD_SIZE])

    def test_output_publish_and_flush_failure_leave_no_partial_output(self):
        for operation in ("link", "fsync"):
            with mock.patch.object(save.os, operation, side_effect=OSError("synthetic failure")):
                with self.assertRaises(OSError):
                    save.export_standard(self.source, self.output)
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.root.glob(".ff7-export-*")), [])

    def test_publish_race_does_not_overwrite(self):
        real_link = os.link

        def race(temporary, destination):
            self.output.write_bytes(b"created-by-another-writer")
            real_link(temporary, destination)

        with mock.patch.object(save.os, "link", side_effect=race):
            with self.assertRaises(FileExistsError):
                save.export_standard(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"created-by-another-writer")
        self.assertEqual(list(self.root.glob(".ff7-export-*")), [])

    def test_cli_explicit_output(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/ff7_save.py"),
                                 "export-standard", str(self.source), "--output", str(self.output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), self.base)
        result = subprocess.run([sys.executable, str(ROOT / "tools/ff7_save.py"),
                                 "export-standard", str(self.source)], capture_output=True)
        self.assertEqual(result.returncode, 2)


@unittest.skipUnless(os.environ.get("FF7_PARTY_TEST_DLL"), "Set FF7_PARTY_TEST_DLL for C/Python parity")
class CParityTests(unittest.TestCase):
    def test_same_bytes_and_cross_decode(self):
        class CMember(ctypes.Structure):
            _fields_ = [("id", ctypes.c_uint16), ("presentation_id", ctypes.c_uint8),
                        ("flags", ctypes.c_uint8), ("record", ctypes.c_uint8 * 132)]

        class CParty(ctypes.Structure):
            _fields_ = [("active", ctypes.c_uint16 * 3), ("count", ctypes.c_uint16),
                        ("extra", CMember * 16), ("stored", ctypes.c_uint16 * 3),
                        ("stored_hint", ctypes.c_uint8 * 3), ("stored_known", ctypes.c_uint8)]

        class CSlot(ctypes.Structure):
            _fields_ = [("directory_slot", ctypes.c_uint8), ("party", CParty)]

        class CCard(ctypes.Structure):
            _fields_ = [("count", ctypes.c_uint16), ("slots", CSlot * 15)]

        dll = ctypes.CDLL(os.environ["FF7_PARTY_TEST_DLL"])
        dll.ff7_party_card_decode.argtypes = [ctypes.POINTER(CCard), ctypes.c_void_p, ctypes.c_size_t,
                                             ctypes.c_void_p, ctypes.c_size_t]
        dll.ff7_party_card_encode.argtypes = [ctypes.POINTER(CCard), ctypes.c_void_p, ctypes.c_size_t,
                                             ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        base = synthetic_card()
        parties = {1: sample_party(), 15: save.Party((1, 2, save.EMPTY), ())}
        expected = save.encode_extension(base, parties)
        card = CCard()
        self.assertEqual(dll.ff7_party_card_decode(ctypes.byref(card), base, len(base), expected, len(expected)), 0)
        self.assertEqual(card.count, 2)
        self.assertEqual(card.slots[0].party.active[2], 256)
        self.assertEqual(bytes(card.slots[0].party.extra[0].record), bytes(range(132)))
        out = (ctypes.c_uint8 * save.MAX_EXTENSION)()
        written = ctypes.c_size_t()
        self.assertEqual(dll.ff7_party_card_encode(ctypes.byref(card), base, len(base), out,
                                                 len(out), ctypes.byref(written)), 0)
        encoded = bytes(out[:written.value])
        self.assertEqual(encoded, expected)  # Includes SHA256 and both CRC levels.
        self.assertEqual(save.parse_card(base + encoded).slots, parties)


if __name__ == "__main__":
    unittest.main()

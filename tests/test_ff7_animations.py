"""Format/parser checks use synthetic bytes; original game assets are optional."""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import inspect_ff7_animations as anim


def settings_with(script):
    return bytes(104) + struct.pack("<74I", *([400] * 74)) + script


def bit_motion(frames, fields, key=4):
    bits = "".join(format(value & ((1 << width) - 1), f"0{width}b")
                   for value, width in fields)
    bits += "0" * ((-len(bits)) % 8)
    payload = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    result = struct.pack("<HHB", frames, len(payload), key) + payload
    return result + bytes((-len(result)) % 4)


class CompressionTests(unittest.TestCase):
    def test_literal_roundtrip_including_ring_wrap(self):
        for size in (0, 1, 7, 8, 9, 4095, 4096, 10001):
            data = bytes((i * 37) & 255 for i in range(size))
            self.assertEqual(anim.decompress_lzs(anim.literal_lzs(data)), data)

    def test_overlap_copy(self):
        # 'A' enters ring 0xFEE; copying that same location expands to six A's.
        payload = b"\x01A\xee\xf2"
        self.assertEqual(anim.decompress_lzs(struct.pack("<I", len(payload)) + payload), b"A" * 6)

    def test_zero_ring_and_truncation_and_limit(self):
        self.assertEqual(anim.decompress_lzs(b"\x03\0\0\0\0\0\0"), bytes(3))
        for raw in (b"", b"\x02\0\0\0\0", b"\x01\0\0\0\xff", b"\x02\0\0\0\0\xff"):
            with self.assertRaises(ValueError):
                anim.decompress_lzs(raw)
        with self.assertRaises(ValueError):
            anim.decompress_lzs(anim.literal_lzs(b"abc"), limit=2)


class ContainerTests(unittest.TestCase):
    def test_section_roundtrip_and_rejection(self):
        chunks = [bytes(4), bytes(8), bytes(12)]
        encoded = anim.pack_sections(chunks)
        self.assertEqual(anim.sections(encoded)[0], chunks)
        for offset, value in ((0, 999), (4, 12), (8, 16), (12, 99)):
            malformed = bytearray(encoded)
            struct.pack_into("<I", malformed, offset, value)
            with self.assertRaises(ValueError):
                anim.sections(malformed)
        with self.assertRaises(ValueError):
            anim.pack_sections([b"bad"])

    def test_tim_full_extent(self):
        image = struct.pack("<II", 16, 2) + struct.pack("<IHHHH", 14, 0, 0, 1, 1) + bytes(2)
        self.assertTrue(anim.tim(image))
        self.assertFalse(anim.tim(image[:-1]))
        self.assertFalse(anim.tim(image + bytes(4)))


class MotionTests(unittest.TestCase):
    def test_initial_and_delta_frame(self):
        # Three signed initial positions, one triple of rotations; second
        # frame mixes short/long position deltas and three rotation modes.
        fields = [(10, 16), (-20, 16), (30, 16), (1, 8), (-1, 8), (0, 8),
                  (0, 1), (-3, 7), (1, 1), (300, 16), (0, 1), (0, 7),
                  (0, 1), (1, 1), (0, 3), (1, 1), (7, 3), (4, 8)]
        result = anim.motion(bit_motion(2, fields), 1)
        self.assertEqual(result["frames"], 2)
        self.assertEqual(result["position_min"], [7, -20, 30])
        self.assertEqual(result["position_max"], [10, 280, 30])
        self.assertLessEqual(result["unused_bits"], 7)

    def test_short_rotation_delta_modes(self):
        fields = [(0, 16)] * 3 + [(0, 8)] * 3
        fields += [(0, 1), (0, 7)] * 3
        fields += [(1, 1), (2, 3), (1, 2), (1, 1), (2, 3), (-1, 2), (0, 1)]
        self.assertLessEqual(anim.motion(bit_motion(2, fields), 1)["unused_bits"], 7)

    def test_placeholders_and_bad_payload(self):
        self.assertEqual(anim.motion(anim.NULL_MOTION, 48)["kind"], "placeholder")
        good = bit_motion(1, [(0, 16)] * 3 + [(0, 8)] * 3)
        for raw in (good[:4], good[:-4], good[:4] + b"\x01" + good[5:],
                    struct.pack("<HHB", 2, 9, 4) + good[5:]):
            with self.assertRaises(ValueError):
                anim.motion(raw, 1)


class ScriptTests(unittest.TestCase):
    def test_operands_are_not_motion_ids(self):
        result = anim.script(bytes.fromhex("c4 09 00 0a 0c f7 05 ee 7f"))
        self.assertEqual(result["motion_ids"], [12])
        self.assertEqual(result["issues"], [])

    def test_conditional_paths_and_unreachable_suffix(self):
        result = anim.script(bytes.fromhex("b3 01 ee b2 02 ee 7f"))
        self.assertEqual(result["motion_ids"], [1, 2])
        self.assertEqual(anim.script(bytes.fromhex("00 fe c0 7f"))["motion_ids"], [0])

    def test_animation_operands_loop_and_fragments(self):
        self.assertEqual(anim.script(bytes.fromhex("b6 09 da 0a ee"))["motion_ids"], [9, 10])
        result = anim.script(bytes.fromhex("a9 c9 02 c1"))
        self.assertEqual(result["motion_ids"], [2])
        self.assertEqual(anim.script(bytes.fromhex("09 9e 0a ee"))["motion_ids"], [9, 10])
        self.assertTrue(anim.script(bytes.fromhex("cb 00"))["issues"])
        self.assertTrue(anim.script(bytes.fromhex("bb"))["issues"])

    def test_pointer_bounds_and_nonmonotonic_aliases(self):
        settings = bytearray(settings_with(bytes.fromhex("00 fe c0 00 09 ee 00 00")))
        for action, pointer in ((1, 404), (2, 0), (3, len(settings)), (4, 400)):
            struct.pack_into("<I", settings, 104 + action * 4, pointer)
        result = anim.actions(settings)
        self.assertEqual(result[1]["motion_ids"], [9])
        self.assertEqual(result[2]["kind"], "unavailable")
        self.assertEqual(result[3]["kind"], "unavailable")
        self.assertEqual(result[0]["motion_ids"], result[4]["motion_ids"])

    def test_preparation_rejects_distributable_paths_before_reading_disc(self):
        for destination in (ROOT / "src", ROOT / "analysis", ROOT / "analysis" / ".." / "mods"):
            with self.assertRaisesRegex(ValueError, "ignored"):
                anim.prepare("does-not-exist.cue", destination)


@unittest.skipUnless(os.environ.get("FF7_TEST_CUE"), "Set FF7_TEST_CUE for owner-disc validation")
class OwnerDiscTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = anim.inspect(os.environ["FF7_TEST_CUE"])

    def test_every_motion_decodes_and_weapon_frames_match(self):
        for name, model in self.report["models"].items():
            self.assertEqual(model["body_motion_count"], 17 if name == "sephiroth" else 40)
            self.assertEqual(model["motion_validation_errors"], [])
            self.assertEqual(model["body_weapon_frame_mismatches"], [])
            self.assertTrue(all(m.get("unused_bits", 0) <= 7 for m in model["motions"]))

    def test_candidate_preserves_originals_and_exact_skeleton(self):
        disc = anim.Disc(Path(os.environ["FF7_TEST_CUE"]))
        self.addCleanup(disc.reader.close)
        raw = disc.read("ENEMY6/SEFIROS.LZS")
        candidate, report = anim.fallback_candidate(raw)
        self.assertEqual(report["body_motion_count"], 20)
        self.assertTrue(report["skeleton_preserved"])
        self.assertNotEqual(raw, candidate)
        self.assertEqual(disc.read("ENEMY6/SEFIROS.LZS"), raw)
        result = anim.model_inventory(candidate)
        self.assertTrue(result["roles"]["death"][0]["idle_only"])
        self.assertEqual(result["sha256"], report["candidate_sha256"])
        for other in ("CLOUD", "VINSENT"):
            path = next(path for path in disc.files if path.endswith("/" + other + ".LZS"))
            with self.assertRaises(ValueError):
                anim.fallback_candidate(disc.read(path))


if __name__ == "__main__":
    unittest.main()

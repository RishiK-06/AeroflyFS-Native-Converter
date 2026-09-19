"""CI smoke test: exercises the shipped codecs without test fixtures.

Runs TTX encode/decode round-trips (square + rectangular power-of-two)
for every output format, and a TSB <-> WAV round-trip.
"""

import os
import struct
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
import ttx_converter as ttx
import toc_decoder
import tsb_decoder


def _make_wav(path: str, rate: int = 22050, channels: int = 1) -> None:
    n = (rate // 2) * channels
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % n, *([0] * n)))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ac_smoke_") as tmp:
        for size in ((32, 32), (64, 32)):
            png = os.path.join(tmp, "m.png")
            Image.new("RGBA", size, (60, 120, 200, 255)).save(png)
            for fmt in ("type_rgba", "type_r",
                        "type_rgb_s3tc_dxt1", "type_rgba_s3tc_dxt5"):
                ttx_path = os.path.join(tmp, "m_%s.ttx" % fmt)
                info = ttx.encode_png(png, ttx_path, fmt=fmt)
                assert (info["width"], info["height"]) == size
                assert info["po2"]
                res = ttx.decode(open(ttx_path, "rb").read())
                assert (res["width"], res["height"]) == size
                assert res["po2"]

        # Generic TM container (fake): root object > uint32 leaf.
        tm_header = (
            bytes.fromhex("61fae71e97f133d7")  # tmworld_airport_detailed
            + bytes(8)                          # name id (unknown -> name_00000000)
            + struct.pack("<Q", 68)             # obj size
            + struct.pack("<Q", 32)             # header size (has children)
            + bytes.fromhex("9e8caf8498703ec2")  # uint32
            + bytes(8)                           # name id
            + struct.pack("<Q", 36)             # obj size
            + struct.pack("<Q", 4)              # header size (leaf)
            + struct.pack("<I", 144)            # value
        )
        assert len(tm_header) == 68
        doc = toc_decoder.parse_toc(tm_header)
        assert doc["kind"] == "tm"
        assert doc["variant"] == "generic_text"
        assert "<[uint32][name_00000000][144]>" in doc["text"]
        assert "<[file][][]" in doc["text"]  # wrapped dump root

        wav = os.path.join(tmp, "t.wav")
        _make_wav(wav)
        tsb = os.path.join(tmp, "t.tsb")
        mi = tsb_decoder.wav_to_tsb(wav, tsb)
        assert mi["format"] in ("mono16", "stereo16")
        assert mi["channels"] == 1
        back = os.path.join(tmp, "b.wav")
        ri = tsb_decoder.tsb_to_wav(tsb, back)
        assert ri["channels"] == 1
        assert int(ri["sample_rate"]) == 22050

    print("SMOKE OK: ttx square+rect all formats, tsb<->wav round-trip, tm generic dump")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
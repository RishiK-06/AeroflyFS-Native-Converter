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
import ttc_converter as ttc
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

        # --- Handoff features: mipmapped + LZHAM compress_file TTX ---
        # Opaque PNG -> auto DXT1, alpha PNG -> auto DXT5.
        opaque = os.path.join(tmp, "opaque.png")
        Image.new("RGB", (64, 32), (200, 50, 30)).save(opaque)
        alpha = os.path.join(tmp, "alpha.png")
        Image.new("RGBA", (64, 32), (10, 200, 120, 128)).save(alpha)
        for src, want_fmt in ((opaque, "type_rgb_s3tc_dxt1"),
                              (alpha, "type_rgba_s3tc_dxt5")):
            p = os.path.join(tmp, "auto.ttx")
            info = ttx.encode_png(src, p, fmt="dxt_auto")
            assert info["format"] == want_fmt, info
            assert info["compressed"] is True
            raw = open(p, "rb").read()
            assert raw[:8] == ttx.MAGIC_COMPRESSED
            back_png = os.path.join(tmp, "auto_back.png")
            res = ttx.ttx_to_png(p, back_png)
            assert (res["width"], res["height"]) == (64, 32)
            assert res["mips"] > 1  # full mip chain, not single-mip
        # ETC2 + ASTC 6x6 round-trips (mobile formats).
        for fmt in ("type_rgb_etc2", "type_rgba_etc2",
                    "type_rgb_astc_6x6", "type_rgba_astc_6x6"):
            src = alpha if "rgba" in fmt else opaque
            p = os.path.join(tmp, "mob.ttx")
            info = ttx.encode_png(src, p, fmt=fmt)
            assert info["format"] == fmt, info
            res = ttx.ttx_to_png(p, os.path.join(tmp, "mob_back.png"))
            assert (res["width"], res["height"]) == (64, 32)

        # --- Scenery TTC round-trips (DXT1 + ETC2) ---
        for fmt in ("dxt1", "etc2"):
            p = os.path.join(tmp, "tile.ttc")
            info = ttc.png_to_ttc(opaque, p, fmt=fmt)
            assert info["format"] == fmt, info
            assert info["mips"] > 1
            res = ttc.ttc_to_png(p, os.path.join(tmp, "tile_back.png"))
            assert (res["width"], res["height"]) == (64, 32)

    print("SMOKE OK: ttx square+rect all formats, tsb<->wav round-trip, tm generic dump")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
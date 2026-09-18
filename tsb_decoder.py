from __future__ import annotations

import struct
import sys

from ttx_converter import (
    TtxError,
    _skip_containers,
    _u32,
    _u64,
    _u64_bytes,
    inflate_ttx,
)

MAGIC_SOUND = bytes([0x5F, 0x34, 0x99, 0x6E, 0xF3, 0x11, 0x96, 0x9D])
SOUND_ROOT_TYPE = MAGIC_SOUND + bytes.fromhex("ce25086b845bd426")


def _f32(b: bytes, off: int) -> float:
    return struct.unpack_from("<f", b, off)[0]


def _parse_string(payload: bytes):
    if len(payload) < 8:
        return None
    n = _u64(payload, 0)
    if not 0 < n <= 64:
        return None
    if 8 + n > len(payload):
        return None
    raw = payload[8 : 8 + n]
    if not all(32 <= b < 127 for b in raw):
        return None
    return raw.decode("ascii")


def parse_tsb(data: bytes):
    """Parse an inflated / plain sound blob into a dict."""
    off = _skip_containers(data)
    fmt = None
    sample_rate = None
    pcm = None
    while off + 32 <= len(data):
        size = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        if size > 200:
            pcm = data[off + 32 : off + size]
            break
        step = 40 if (size == 36 and hs == 40) else int(size)
        if step < 32:
            raise TtxError(f"bad sound chunk step at 0x{off:x}")
        payload = data[off + 32 : off + step]
        s = _parse_string(payload) if len(payload) >= 8 else None
        if s:
            fmt = s
            off += step
            continue
        if sample_rate is None and 4 <= len(payload) <= 8:
            sample_rate = _f32(payload, 0)
            off += step
            continue
        off += step

    if fmt is None or sample_rate is None or pcm is None:
        raise TtxError(
            "incomplete sound parse: format=%r rate=%r pcm=%s"
            % (fmt, sample_rate, len(pcm) if pcm is not None else None)
        )

    import re

    channels, bits = 1, 16
    m = re.match(r"^(mono|stereo)(\d+)$", fmt)
    if m:
        channels = 2 if m.group(1) == "stereo" else 1
        bits = int(m.group(2))
    return {
        "format": fmt,
        "sample_rate": sample_rate,
        "channels": channels,
        "bits": bits,
        "pcm": bytes(pcm),
    }


def tsb_to_wav_bytes(data: bytes) -> bytes:
    """Decode a .tsb blob (plain or LZHAM) and return RIFF/WAVE bytes."""
    info = parse_tsb(inflate_ttx(data))
    return _wav_bytes(info["pcm"], info["sample_rate"], info["channels"], info["bits"])


def _wav_bytes(pcm: bytes, sample_rate: float, channels: int, bits: int) -> bytes:
    rate = round(sample_rate)
    byps = bits // 8
    block = channels * byps
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        rate,
        rate * block,
        block,
        bits,
        b"data",
        data_size,
    )
    return header + pcm


def _write_wav_file(out_path: str, pcm: bytes, sample_rate: float,
                    channels: int, bits: int):
    with open(out_path, "wb") as fh:
        fh.write(_wav_bytes(pcm, sample_rate, channels, bits))


def tsb_to_wav(in_path: str, out_path: str, status=None) -> dict:
    """Convert a .tsb file to a .wav file. Returns parse info."""
    if status:
        status(f"Reading {in_path} ...")
    with open(in_path, "rb") as fh:
        raw = fh.read()
    if status:
        status("Decoding ...")
    info = parse_tsb(inflate_ttx(raw))
    if status:
        status("Writing WAV ...")
    _write_wav_file(out_path, info["pcm"], info["sample_rate"],
                    info["channels"], info["bits"])
    if status:
        status("Done.")
    return info


# --------------------------------------------------------------------------- encode

def _tsb_chunk(payload: bytes, size: int | None = None, hs: int | None = None) -> bytes:
    sz = (32 + len(payload)) if size is None else size
    return b"\x00" * 16 + _u64_bytes(sz) + _u64_bytes(sz if hs is None else hs) + payload


def _f32_bytes(value: float) -> bytes:
    return struct.pack("<f", value)


def build_tsb(fmt: str, sample_rate: float, pcm: bytes) -> bytes:
    """Build a plain (uncompressed) .tsb blob from PCM + format string.

    ``fmt`` is e.g. ``mono8``, ``mono16``, ``stereo24`` ... ``channels`` and
    ``bits`` are re-derived from it by the decoder via ``^(mono|stereo)\\d+$``.
    """
    s = fmt.encode("ascii")
    pad = (8 - (len(s) + 8) % 8) % 8
    props = _tsb_chunk(_u64_bytes(len(s)) + s + b"\x00" * pad)
    props += b"\x00" * 16 + _u64_bytes(36) + _u64_bytes(40) + _f32_bytes(sample_rate) + b"\x00" * 4
    data = _tsb_chunk(pcm, size=32 + len(pcm), hs=32)
    blob = SOUND_ROOT_TYPE + _u64_bytes(0) + _u64_bytes(32) + props + data
    return blob[:16] + _u64_bytes(len(blob)) + blob[24:]


def wav_to_tsb(in_path: str, out_path: str, status=None) -> dict:
    """Convert an uncompressed PCM .wav file to a .tsb file."""
    if status:
        status(f"Reading {in_path} ...")
    try:
        import wave
    except ImportError:  # pragma: no cover
        raise TtxError("standard library 'wave' module unavailable")
    with wave.open(in_path, "rb") as w:
        if w.getcomptype() != "NONE":
            raise TtxError("only uncompressed (PCM) WAV files can become TSB")
        channels = w.getnchannels()
        rate = w.getframerate()
        bits = w.getsampwidth() * 8
        nframes = w.getnframes()
        pcm = w.readframes(nframes)
    if channels not in (1, 2):
        raise TtxError("TSB supports mono or stereo only "
                       "(got %d channels)" % channels)
    if bits not in (8, 16, 24, 32):
        raise TtxError("TSB supports 8/16/24/32 bit samples (got %d)" % bits)
    fmt = ("mono" if channels == 1 else "stereo") + str(bits)
    if status:
        status(f"Encoding {fmt} @ {rate} Hz ...")
    blob = build_tsb(fmt, float(rate), bytes(pcm))
    if status:
        status("Writing TSB ...")
    with open(out_path, "wb") as fh:
        fh.write(blob)
    if status:
        status("Done.")
    return {
        "format": fmt,
        "sample_rate": rate,
        "channels": channels,
        "bits": bits,
        "frames": nframes,
        "pcm_bytes": len(pcm),
    }
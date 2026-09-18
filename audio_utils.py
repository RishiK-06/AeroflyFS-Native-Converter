"""Audio decode helpers (miniaudio) -> 16-bit PCM WAV.

Used by the GUI / CLI for ``.mp3``, ``.flac``, ``.ogg`` (and ``.wav``)
input files. ``miniaudio`` ships prebuilt cross-platform wheels (Windows /
macOS / Linux) with the decoder embedded, so no system packages are needed.

If ``miniaudio`` is missing the conversion raises ``TtxError`` with install
instructions; the rest of the app keeps working.
"""

from __future__ import annotations

import struct

from ttx_converter import TtxError
from tsb_decoder import _wav_bytes


def _write_wav(out_path: str, pcm: bytes, sample_rate: float,
               channels: int, bits: int):
    with open(out_path, "wb") as fh:
        fh.write(_wav_bytes(pcm, sample_rate, channels, bits))


def audio_to_wav(in_path: str, out_path: str, status=None) -> dict:
    """Decode .mp3/.flac/.ogg/.wav to a 16-bit PCM WAV file."""
    try:
        import miniaudio
    except ImportError:
        raise TtxError(
            "miniaudio is required for MP3/FLAC/OGG decoding.\n"
            "Install it with:  pip install miniaudio"
        )
    if status:
        status(f"Reading {in_path} ...")
    info = miniaudio.get_file_info(in_path)
    decoded = miniaudio.decode_file(
        in_path,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=info.nchannels,
        sample_rate=info.sample_rate,
    )
    if status:
        status("Writing WAV ...")
    pcm = bytes(decoded.samples)
    _write_wav(out_path, pcm, decoded.sample_rate, decoded.nchannels, 16)
    if status:
        status("Done.")
    width = decoded.sample_width or 2
    return {
        "format": "pcm_s16le",
        "source": (
            info.file_format.name.lower()
            if getattr(info, "file_format", None) is not None
            else "audio"
        ),
        "sample_rate": decoded.sample_rate,
        "channels": decoded.nchannels,
        "bits": 16,
        "frames": len(pcm) // (decoded.nchannels * width),
        "pcm_bytes": len(pcm),
    }


def wav_info(path: str):
    """Quick header-only info for a .wav file."""
    import wave

    with wave.open(path, "rb") as w:
        return {
            "channels": w.getnchannels(),
            "sample_rate": w.getframerate(),
            "bits": w.getsampwidth() * 8,
            "frames": w.getnframes(),
        }
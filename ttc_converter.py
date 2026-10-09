"""Aerofly FS scenery ``.ttc`` textures: PNG <-> TTC (DXT1 / DXT5 / ETC2 / R8 mask).

Native TTC (GeoConvert / GPU-compressed content converter) is a 256-byte
header plus zlib or tmcompress(LZHAM) GPU blocks — not a TTX chunk tree.

``compress=false`` converter output may still be a TTX twin saved as ``.ttc``;
``ttc_to_png`` accepts those and delegates to ``ttx_converter``.

ASTC 6x6 is deferred until a sample exists (format id unknown).
"""
from __future__ import annotations

import argparse
import math
import os
import re
import struct
import sys
import zlib

from ttx_converter import (
    MAGIC_COMPRESSED,
    MAGIC_PLAIN,
    TtxError,
    _inflate_raw,
    decode as decode_ttx,
    decode_rgba,
    flip_vertical,
    ttx_to_png,
    _encode_bc1,
    _encode_bc3,
    _save_png,
)

TtcError = TtxError

TTC_MAGIC = 0x303A
TTC_VERSION = 0x100
TTC_HEADER_SIZE = 256
TMCOMPRESS_MAGIC = bytes([0xF4, 0xBE, 0x10, 0xA8])

# On-disk format ids observed in templates (05/06/0a/0b).
FORMAT_IDS = {
    "r8": 0,
    "dxt1": 10,
    "dxt5": 12,
    "etc2": 21,
}
ID_TO_FORMAT = {v: k for k, v in FORMAT_IDS.items()}
ID_TO_TTX = {
    0: "type_r",
    10: "type_rgb_s3tc_dxt1",
    12: "type_rgba_s3tc_dxt5",
    21: "type_rgb_etc2",
}
BLOCK = {
    "r8": (1, 1, 1),
    "dxt1": (4, 4, 8),
    "dxt5": (4, 4, 16),
    "etc2": (4, 4, 8),
}

_MAP_ZOOM = re.compile(r"(?:^|[\\/])map_(\d+)_", re.IGNORECASE)


class TtcInfo(dict):
    pass


def _u32(b: bytes, off: int) -> int:
    return int.from_bytes(b[off : off + 4], "little")


def parse_ttc_header(data: bytes) -> dict:
    if len(data) < TTC_HEADER_SIZE:
        raise TtcError("TTC file too short for 256-byte header")
    magic, ver, extra, payload, uncomp, w, h, mips, fmt = struct.unpack_from(
        "<9I", data, 0
    )
    if magic != TTC_MAGIC:
        raise TtcError(f"not a native TTC (magic {magic:#x})")
    if ver != TTC_VERSION:
        raise TtcError(f"unsupported TTC version {ver:#x}")
    if 256 + payload != len(data):
        raise TtcError(
            f"payload length mismatch: header {payload} file {len(data) - 256}"
        )
    name = ID_TO_FORMAT.get(fmt)
    if name is None:
        raise TtcError(f"unknown TTC format id {fmt}")
    return {
        "extra": extra,
        "payload": payload,
        "uncompressed": uncomp,
        "width": w,
        "height": h,
        "mips": mips or 1,
        "format_id": fmt,
        "format": name,
        "preview": (_u32(data, 36), _u32(data, 40)),
    }


def is_native_ttc(data: bytes) -> bool:
    return len(data) >= 8 and _u32(data, 0) == TTC_MAGIC and _u32(data, 4) == TTC_VERSION


def is_ttx_container(data: bytes) -> bool:
    return data[:8] in (MAGIC_PLAIN, MAGIC_COMPRESSED)


def inflate_tmcompress(blob: bytes) -> bytes:
    """Inflate a 64-byte tmcompress header + LZHAM stream via tmcompress.wasm."""
    plen = len(blob)
    prefix = b"\x00" * 0x40 + b"\x00" * 16 + struct.pack("<QQ", plen + 32, 32)
    out = _inflate_raw(prefix + blob)
    if out is None:
        raise TtcError("LZHAM inflate failed (bad or unsupported stream)")
    return out


def inflate_ttc_payload(body: bytes, uncompressed: int) -> tuple[bytes, str]:
    if not body:
        raise TtcError("empty TTC payload")
    if body[4:8] == TMCOMPRESS_MAGIC or (
        len(body) >= 8 and body[:4] == b"\x40\x00\x00\x00" and body[4:8] == TMCOMPRESS_MAGIC
    ):
        pix = inflate_tmcompress(body)
        method = "lzham"
    elif body[0] == 0x78:
        pix = zlib.decompress(body)
        method = "zlib"
    elif len(body) == uncompressed:
        pix = body
        method = "raw"
    else:
        raise TtcError("unrecognised TTC payload (not zlib, LZHAM, or raw GPU)")
    if uncompressed and len(pix) != uncompressed:
        raise TtcError(
            f"inflated size {len(pix)} != header uncompressed {uncompressed}"
        )
    return pix, method


def parse_ttc(data: bytes) -> dict:
    hdr = parse_ttc_header(data)
    pix, method = inflate_ttc_payload(data[TTC_HEADER_SIZE :], hdr["uncompressed"])
    hdr["pixels"] = pix
    hdr["payload_method"] = method
    return hdr


def decode(data: bytes, flip: bool = True) -> dict:
    """Bytes -> RGBA (top mip) + metadata. Default flip restores source-art orientation."""
    if is_native_ttc(data):
        info = parse_ttc(data)
        ttx_info = {
            "format": ID_TO_TTX[info["format_id"]],
            "width": info["width"],
            "height": info["height"],
            "mips": info["mips"],
            "pixels": info["pixels"],
        }
        rgba = decode_rgba(ttx_info)
        if flip:
            rgba = flip_vertical(rgba, info["width"], info["height"])
        return {
            "width": info["width"],
            "height": info["height"],
            "format": info["format"],
            "format_id": info["format_id"],
            "mips": info["mips"],
            "payload_method": info["payload_method"],
            "extra": info["extra"],
            "native": True,
            "rgba": rgba,
        }
    if is_ttx_container(data):
        result = decode_ttx(data, flip=flip)
        result["native"] = False
        result["payload_method"] = "ttx"
        return result
    raise TtcError("not a native TTC or TTX-twin .ttc")


def ttc_to_png(in_path: str, out_path: str, flip: bool = True, status=None) -> dict:
    if status:
        status(f"Reading {os.path.basename(in_path)} ...")
    with open(in_path, "rb") as f:
        raw = f.read()
    if is_ttx_container(raw) and not is_native_ttc(raw):
        if status:
            status("TTX-twin .ttc — decoding via ttx_converter ...")
        return ttx_to_png(in_path, out_path, flip=flip, status=status)
    if status:
        status("Decoding ...")
    result = decode(raw, flip=flip)
    if status:
        status("Writing PNG ...")
    _save_png(out_path, result["rgba"], result["width"], result["height"])
    if status:
        status("Done.")
    return result


# ---------------------------------------------------------------------------
# PNG -> TTC
# ---------------------------------------------------------------------------

def mip_count(w: int, h: int) -> int:
    return int(math.floor(math.log2(max(w, h)))) + 1


def gpu_mip_bytes(fmt: str, w: int, h: int, mips: int) -> int:
    bw, bh, bpb = BLOCK[fmt]
    total = 0
    cw, ch = w, h
    for _ in range(mips):
        total += ((cw + bw - 1) // bw) * ((ch + bh - 1) // bh) * bpb
        cw = max(1, cw // 2)
        ch = max(1, ch // 2)
    return total


def zoom_from_name(path: str) -> int:
    m = _MAP_ZOOM.search(path.replace("/", "\\"))
    return int(m.group(1)) if m else 0


def _preview_colors(img) -> tuple[int, int]:
    extrema = img.getextrema()
    # PIL: per-band (min, max). Solid black matches GeoConvert/converter samples.
    if all(band[1] == 0 for band in extrema[:3]):
        return 0xFFFFFFFF, 0xFFFFFFFF
    return 0, 0


def _encode_r8(img) -> bytes:
    """Single-channel mask: use alpha if it varies, otherwise luminance."""
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    amin, amax = alpha.getextrema()
    if amin < 255:
        return alpha.tobytes()
    return rgba.convert("L").tobytes()


def _encode_level(img, fmt: str) -> bytes:
    bw, bh, _bpb = BLOCK[fmt]
    w, h = img.size
    if w % bw or h % bh:
        img = _pad_to(img, max(bw, (w + bw - 1) // bw * bw), max(bh, (h + bh - 1) // bh * bh))
        w, h = img.size
    if fmt == "r8":
        return _encode_r8(img)
    if fmt == "dxt1":
        try:
            import etcpak

            return etcpak.compress_bc1(img.tobytes(), w, h)
        except ImportError:
            return _encode_bc1(img)
    if fmt == "dxt5":
        try:
            import etcpak

            return etcpak.compress_bc3(img.tobytes(), w, h)
        except ImportError:
            return _encode_bc3(img)
    if fmt == "etc2":
        try:
            import etcpak
        except ImportError:
            raise TtcError(
                "ETC2 encode needs the 'etcpak' package. Install it with:  pip install etcpak"
            )
        # etcpak.compress_etc2_rgb expects RGBA byte order (R/B swap = blue cast on device).
        return etcpak.compress_etc2_rgb(img.tobytes(), w, h)
    raise TtcError(f"unsupported TTC format: {fmt}")


def _pad_to(img, nw: int, nh: int):
    w, h = img.size
    if nw == w and nh == h:
        return img
    from PIL import Image

    canvas = Image.new("RGBA", (nw, nh))
    canvas.paste(img, (0, 0))
    if nw > w:
        edge = img.crop((w - 1, 0, w, h)).resize((nw - w, h))
        canvas.paste(edge, (w, 0))
    if nh > h:
        strip = canvas.crop((0, h - 1, nw, h)).resize((nw, nh - h))
        canvas.paste(strip, (0, h))
    return canvas


def _pad4(img):
    w, h = img.size
    return _pad_to(img, (w + 3) & ~3, (h + 3) & ~3)


def _resize_box(img, size):
    from PIL import Image

    return img.resize(size, Image.Resampling.BOX)


def encode_gpu_mips(img, fmt: str, do_mips: bool) -> tuple[bytes, int]:
    w, h = img.size
    n = mip_count(w, h) if do_mips else 1
    parts = []
    cur = img
    for i in range(n):
        parts.append(_encode_level(cur, fmt))
        if i + 1 < n:
            cur = _resize_box(cur, (max(1, cur.size[0] // 2), max(1, cur.size[1] // 2)))
    return b"".join(parts), n


def build_ttc(
    pixels: bytes,
    w: int,
    h: int,
    mips: int,
    fmt: str,
    extra: int = 0,
    preview: tuple[int, int] = (0, 0),
    payload_method: str = "zlib",
) -> bytes:
    if fmt not in FORMAT_IDS:
        raise TtcError(f"unsupported TTC format: {fmt}")
    if payload_method == "zlib":
        body = zlib.compress(pixels, 1)
    elif payload_method == "raw":
        body = pixels
    elif payload_method == "lzham":
        raise TtcError(
            "LZHAM/tmcompress encode is not in tmcompress.wasm (inflate only). "
            "Use zlib (content-converter DXT path) or wait for a compress helper."
        )
    else:
        raise TtcError(f"unknown payload method: {payload_method}")
    hdr = bytearray(TTC_HEADER_SIZE)
    struct.pack_into(
        "<9I",
        hdr,
        0,
        TTC_MAGIC,
        TTC_VERSION,
        extra,
        len(body),
        len(pixels),
        w,
        h,
        mips,
        FORMAT_IDS[fmt],
    )
    struct.pack_into("<II", hdr, 36, preview[0], preview[1])
    return bytes(hdr) + body


def png_to_ttc(
    in_path: str,
    out_path: str,
    fmt: str = "dxt1",
    flip: bool = True,
    mipmaps: bool = True,
    extra: int | None = None,
    payload_method: str = "zlib",
    status=None,
) -> dict:
    fmt = fmt.lower().replace("type_rgb_s3tc_", "").replace("type_rgba_s3tc_", "")
    fmt = {
        "dxt": "dxt1",
        "bc1": "dxt1",
        "bc3": "dxt5",
        "etc": "etc2",
        "mask": "r8",
        "r": "r8",
        "type_r": "r8",
    }.get(fmt, fmt)
    if fmt not in FORMAT_IDS:
        raise TtcError(f"unsupported TTC format: {fmt} (use dxt1, dxt5, etc2, r8)")
    try:
        from PIL import Image
    except ImportError:
        raise TtcError(
            "PNG encode needs the 'Pillow' package. Install it with:  pip install Pillow"
        )
    if status:
        status(f"Reading {os.path.basename(in_path)} ...")
    img = Image.open(in_path).convert("RGBA")
    if flip:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if fmt != "r8":
        img = _pad4(img)
    w, h = img.size
    preview = _preview_colors(img)
    if extra is None:
        extra = zoom_from_name(in_path)
    if status:
        status(f"Encoding {fmt} ...")
    pixels, mips = encode_gpu_mips(img, fmt, mipmaps)
    expect = gpu_mip_bytes(fmt, w, h, mips)
    if len(pixels) != expect:
        raise TtcError(f"GPU payload {len(pixels)} != expected {expect} for {w}x{h} mips={mips}")
    if status:
        status(f"Writing TTC ({payload_method}) ...")
    data = build_ttc(pixels, w, h, mips, fmt, extra=extra, preview=preview, payload_method=payload_method)
    with open(out_path, "wb") as f:
        f.write(data)
    if status:
        status("Done.")
    return {
        "width": w,
        "height": h,
        "format": fmt,
        "mips": mips,
        "extra": extra,
        "payload_method": payload_method,
        "bytes": len(data),
        "native": True,
    }


def _log(msg: str) -> None:
    print(f"    {msg}")


def _auto_cli(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Convert Aerofly FS scenery .ttc textures (DXT1/DXT5/ETC2/R8 mask)"
    )
    p.add_argument("paths", nargs="+", help=".ttc / .png file(s) or folder(s)")
    p.add_argument("-o", "--output", help="Output path (single file only)")
    p.add_argument(
        "-f",
        "--format",
        default="dxt1",
        choices=("dxt1", "dxt5", "etc2", "r8"),
        help="GPU format when encoding PNG -> TTC (default dxt1)",
    )
    p.add_argument("--no-flip", action="store_true", help="Do not flip vertically")
    p.add_argument("--no-mipmaps", action="store_true", help="Encode only the top mip")
    p.add_argument(
        "--zoom",
        type=int,
        default=None,
        help="Header extra/zoom (default: from map_N_ filename, else 0)",
    )
    p.add_argument("--info", action="store_true", help="Print info only (no output file)")
    args = p.parse_args(argv)

    from pathlib import Path
    import fnmatch

    files = []
    for pt in args.paths:
        if os.path.isdir(pt):
            files.extend(
                str(x)
                for x in Path(pt).rglob("*")
                if x.is_file()
                and any(
                    fnmatch.fnmatch(x.name.lower(), pat)
                    for pat in ("*.ttc", "*.png", "*.jpg", "*.jpeg")
                )
            )
        else:
            files.append(pt)
    if not files:
        print("No matching files found.")
        return 1

    flip = not args.no_flip
    nerr = 0
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f}")
        out = args.output if i == 1 else None
        low = f.lower()
        try:
            if low.endswith(".ttc"):
                if args.info:
                    raw = open(f, "rb").read()
                    if is_native_ttc(raw):
                        info = parse_ttc(raw)
                        print(
                            f"    native TTC {info['format']} {info['width']}x{info['height']} "
                            f"mips={info['mips']} extra={info['extra']} "
                            f"{info['payload_method']} uncomp={info['uncompressed']}"
                        )
                    elif is_ttx_container(raw):
                        r = decode_ttx(raw, flip=False)
                        print(
                            f"    TTX-twin {r['format']} {r['width']}x{r['height']} "
                            f"mips={r['mips']}"
                        )
                    else:
                        raise TtcError("unrecognised .ttc")
                    continue
                dest = out or (os.path.splitext(f)[0] + ".decoded.png")
                r = ttc_to_png(f, dest, flip=flip, status=_log)
                print(
                    f"    -> {dest}  {r.get('format')} {r['width']}x{r['height']} "
                    f"mips={r.get('mips')} {r.get('payload_method', '')}"
                )
            elif low.endswith((".png", ".jpg", ".jpeg")):
                dest = out or (os.path.splitext(f)[0] + ".ttc")
                r = png_to_ttc(
                    f,
                    dest,
                    fmt=args.format,
                    flip=flip,
                    mipmaps=not args.no_mipmaps,
                    extra=args.zoom,
                    status=_log,
                )
                print(
                    f"    -> {dest}  {r['format']} {r['width']}x{r['height']} "
                    f"mips={r['mips']} extra={r['extra']} {r['payload_method']} "
                    f"{r['bytes']} bytes"
                )
            else:
                print("    skip (use .ttc or .png)")
        except TtcError as exc:
            print(f"    ERROR: {exc}")
            nerr += 1
    return 1 if nerr else 0


if __name__ == "__main__":
    sys.exit(_auto_cli())

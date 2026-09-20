from __future__ import annotations

import os
import sys

MAGIC_COMPRESSED = bytes([0xB5, 0xFE, 0x24, 0xC7, 0xB7, 0x3C, 0xEB, 0xB7])
MAGIC_PLAIN = bytes([0xA6, 0x97, 0xE9, 0xAC, 0xF9, 0xFC, 0xC1, 0x7C])

_lzham_cache = {}


def _is_po2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _po2_warning(w: int, h: int) -> str:
    return (
        f"WARNING: {w}x{h} is not power-of-two - Aerofly textures are expected "
        "to be power-of-two (e.g. 1024x1024, 1024x512)"
    )


class TtxError(Exception):
    """Raised on invalid / unsupported TTX input."""


def _base_dir(path):
    if hasattr(sys, "_MEIPASS"):
        return getattr(sys, "_MEIPASS")
    return os.path.dirname(os.path.abspath(path))


def _load_lzham():
    """Load tmcompress.wasm through wasmtime (cached singleton)."""
    if "loader" in _lzham_cache:
        return _lzham_cache["loader"]
    try:
        from wasmtime import Engine, Func, FuncType, Instance, Module, Store, ValType
    except ImportError:
        raise TtxError(
            "The 'wasmtime' package is required to decompress LZHAM-compressed "
            "textures. Install it with:  pip install wasmtime"
        )
    wasm_path = os.path.join(_base_dir(__file__), "tmcompress.wasm")
    if not os.path.exists(wasm_path):
        raise TtxError(
            "tmcompress.wasm not found next to ttx_converter.py. Restore the "
            "tmcompress.wasm file (see INSTALLATION.md)."
        )
    engine = Engine()
    store = Store(engine)
    module = Module.from_file(engine, wasm_path)
    i32 = ValType.i32()
    # WebAssembly runtime imports; all are safe no-ops for a pure inflate call.
    a_a = Func(store, FuncType([i32, i32, i32, i32], [i32]), lambda caller, a, b, c, d: 0)
    a_b = Func(store, FuncType([i32], [i32]), lambda caller, a: 1)
    a_c = Func(store, FuncType([i32], []), lambda caller, a: None)
    inst = Instance(store, module, [a_a, a_b, a_c])
    ex = inst.exports(store)
    loader = {
        "memory": ex["d"],
        "unc_size": ex["f"],
        "inflate": ex["g"],
        "malloc": ex["h"],
        "free": ex["i"],
        "store": store,
    }
    _lzham_cache["loader"] = loader
    return loader


def inflate_ttx(data: bytes) -> bytes:
    """LZHAM-inflate a ``compress_file=true`` container."""
    if data[:8] == MAGIC_COMPRESSED:
        low = _inflate_raw(data)
        if low is None:
            raise TtxError("LZHAM inflate failed (bad or unsupported stream)")
        return low
    return data


def _walk_payload(data):
    """Return (payload, payload_len) for the large data chunk, or (None, None)."""
    if len(data) < 0x100:
        return None, None
    pos = 0x40
    while pos + 32 <= len(data):
        size = _u64(data, pos + 16)
        hs = _u64(data, pos + 24)
        if size > 200:
            if pos + (int)(size) > len(data) or size < 32:
                return None, None
            return pos + 32, (int)(size) - 32
        step = 40 if (size == 36 and hs == 40) else (int)(size)
        if step < 32:
            return None, None
        pos += step
    return None, None


def _inflate_raw(data: bytes):
    """Inflate using the tmcompress wasm; returns bytes or None on -1 from unc_size."""
    try:
        loader = _load_lzham()
    except TtxError:
        raise
    store = loader["store"]
    unc_size_fn = loader["unc_size"]
    inflate_fn = loader["inflate"]
    malloc_fn = loader["malloc"]
    free_fn = loader["free"]
    mem = loader["memory"]

    payload, plen = _walk_payload(data)
    if payload is None:
        return None

    in_ptr = malloc_fn(store, plen)
    if not in_ptr:
        return None
    try:
        mem.write(store, bytes(data[payload : payload + plen]), in_ptr)
        unc = unc_size_fn(store, in_ptr, plen)
        if unc <= 0 or unc > (1 << 31):
            return None
        out_ptr = malloc_fn(store, unc)
        if not out_ptr:
            return None
        try:
            n = inflate_fn(store, in_ptr, plen, out_ptr, unc)
            if n <= 0:
                return None
            return bytes(mem.read(store, out_ptr, out_ptr + n))
        finally:
            free_fn(store, out_ptr)
    finally:
        free_fn(store, in_ptr)


def _u32(b: bytes, off: int) -> int:
    return int.from_bytes(b[off : off + 4], "little")


def _u64(b: bytes, off: int) -> int:
    return int.from_bytes(b[off : off + 8], "little")


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


def _skip_containers(data: bytes) -> int:
    off = 0
    while off + 32 <= len(data):
        size = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        if hs == 32 and (size == len(data) - off or size == len(data)):
            off += 32
            continue
        break
    return off


def _walk_props(data: bytes, start: int):
    off = start
    while off + 32 <= len(data):
        size = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        if size > 200:
            end = min(off + size, len(data))
            yield data[off + 32 : end]
            return
        step = 40 if (size == 36 and hs == 40) else (int)(size)
        if step < 32:
            raise TtxError(f"bad chunk step at 0x{off:x}")
        yield data[off + 32 : off + step]
        off += step


def parse_ttx(data: bytes):
    """Parse an (already inflated) TTX blob into (fmt, w, h, mips, pixels)."""
    off = _skip_containers(data)
    fmt = None
    target = None
    width = height = layers = mips = None
    pixels = None
    for payload in _walk_props(data, off):
        if len(payload) >= 8:
            s = _parse_string(payload)
            if s:
                if s.startswith("type_"):
                    fmt = s
                    continue
                if s.startswith("target_"):
                    target = s
                    continue
        if 4 <= len(payload) <= 8:
            val = _u32(payload, 0)
            if width is None:
                width = val
            elif height is None:
                height = val
            elif layers is None:
                layers = val
            elif mips is None:
                mips = val
            continue
        pixels = payload
        break

    if not fmt or width is None or height is None or pixels is None:
        raise TtxError(
            "incomplete texture: fmt=%r %sx%s pix=%s"
            % (fmt, width, height, len(pixels) if pixels is not None else None)
        )
    return {
        "format": fmt,
        "target": target,
        "width": width,
        "height": height,
        "layers": layers or 1,
        "mips": mips or 1,
        "pixels": pixels,
    }


def decode_rgba(info: dict):
    """Decode a parsed texture to an RGBA bytearray."""
    fmt = info["format"]
    w, h, pix = info["width"], info["height"], info["pixels"]
    if fmt == "type_rgba":
        return bytearray(pix[: w * h * 4])
    if fmt == "type_r":
        need = w * h
        out = bytearray(need * 4)
        for i in range(need):
            v = pix[i]
            o = i * 4
            out[o] = out[o + 1] = out[o + 2] = v
            out[o + 3] = 255
        return out

    if fmt == "type_rgba_s3tc_dxt3":
        return bytearray(_decode_dxt3(pix, w, h))

    # Remaining block compressed formats -> texture2ddecoder (BGRA) -> RGBA
    try:
        import texture2ddecoder as t2d
    except ImportError:
        raise TtxError(
            f"Format '{fmt}' needs the 'texture2ddecoder' package. "
            "Install it with:  pip install texture2ddecoder"
        )

    try:
        if fmt in ("type_rgb_s3tc_dxt1", "type_rgba_s3tc_dxt1"):
            data = t2d.decode_bc1(pix, w, h)
        elif fmt == "type_rgba_s3tc_dxt5":
            data = t2d.decode_bc3(pix, w, h)
        elif fmt in ("type_rgb_etc2", "type_rgb_etc1"):
            data = t2d.decode_etc2(pix, w, h)
        elif fmt == "type_rgba_etc2":
            data = t2d.decode_etc2a8(pix, w, h)
        elif fmt == "type_rg_rgtc2":
            bgra = t2d.decode_bc5(pix, w, h)
            out = bytearray(len(bgra))
            for i in range(0, len(bgra), 4):
                x = (bgra[i] / 255.0) * 2.0 - 1.0
                y = (bgra[i + 1] / 255.0) * 2.0 - 1.0
                z = max(0.0, 1.0 - x * x - y * y)
                z = min(255, max(0, int(((z ** 0.5 + 1.0) * 0.5) * 255.0)))
                out[i] = bgra[i + 2]
                out[i + 1] = bgra[i + 1]
                out[i + 2] = z
                out[i + 3] = 255
            return out
        else:
            import re

            m = re.match(r"^type_rgb_astc_(\d+)x(\d+)$", fmt)
            if not m:
                m = re.match(r"^type_rgba_astc_(\d+)x(\d+)$", fmt)
            if m:
                bw, bh = int(m.group(1)), int(m.group(2))
                data = t2d.decode_astc(pix, w, h, bw, bh)
            else:
                raise TtxError(f"unsupported format: {fmt}")
    except TtxError:
        raise
    except Exception as exc:
        raise TtxError(f"{fmt} decode failed: {exc}") from exc

    if not isinstance(data, (bytes, bytearray)):
        raise TtxError(f"{fmt} decode returned invalid data")
    bgra = memoryview(data)
    return _bgra_to_rgba(bgra)


def _bgra_to_rgba(bgra):
    out = bytearray(len(bgra))
    for i in range(0, len(bgra), 4):
        out[i] = bgra[i + 2]
        out[i + 1] = bgra[i + 1]
        out[i + 2] = bgra[i]
        out[i + 3] = bgra[i + 3]
    return out


def _decode_dxt3(pix: bytes, w: int, h: int) -> bytes:
    """BC2 / DXT3 explicit 4-bit alpha + 4-color RGB block (pure Python)."""
    out = bytearray(w * h * 4)
    bw, bh = (w + 3) >> 2, (h + 3) >> 2
    off = 0
    for by in range(bh):
        for bx in range(bw):
            block = pix[off : off + 16]
            off += 16
            if len(block) < 16:
                break
            alphas = bytearray(16)
            for i in range(16):
                byte = block[i >> 1]
                a = (byte & 0x0F) if (i & 1) == 0 else (byte >> 4)
                alphas[i] = a * 17
            c0 = block[8] | (block[9] << 8)
            c1 = block[10] | (block[11] << 8)
            bits = (
                block[12]
                | (block[13] << 8)
                | (block[14] << 16)
                | (block[15] << 24)
            )
            colors = [_decode_rgb565(c0), _decode_rgb565(c1)]
            colors.append(
                [
                    ((2 * colors[0][0] + colors[1][0]) // 3),
                    ((2 * colors[0][1] + colors[1][1]) // 3),
                    ((2 * colors[0][2] + colors[1][2]) // 3),
                ]
            )
            colors.append(
                [
                    ((colors[0][0] + 2 * colors[1][0]) // 3),
                    ((colors[0][1] + 2 * colors[1][1]) // 3),
                    ((colors[0][2] + 2 * colors[1][2]) // 3),
                ]
            )
            for i in range(16):
                x = bx * 4 + (i & 3)
                y = by * 4 + (i >> 2)
                if x >= w or y >= h:
                    continue
                idx = (bits >> (2 * i)) & 3
                r, g, b = colors[idx]
                dst = (y * w + x) * 4
                out[dst] = r
                out[dst + 1] = g
                out[dst + 2] = b
                out[dst + 3] = alphas[i]
    return bytes(out)


def _decode_rgb565(c: int):
    return [
        ((c >> 11) & 0x1F) * 255 // 31,
        ((c >> 5) & 0x3F) * 255 // 63,
        (c & 0x1F) * 255 // 31,
    ]


def bgra_to_rgba(raw: bytes) -> bytes:
    """Convenience converter for external callers of texture2ddecoder."""
    return bytes(_bgra_to_rgba(memoryview(raw)))


def flip_vertical(rgba: bytes, w: int, h: int) -> bytes:
    row = w * 4
    out = bytearray(len(rgba))
    for y in range(h):
        src = y * row
        dst = (h - 1 - y) * row
        out[dst : dst + row] = rgba[src : src + row]
    return bytes(out)


def decode(data: bytes, flip: bool = False):
    """High-level: bytes -> dict with RGBA + metadata."""
    compressed = bytes(data[:8]) == MAGIC_COMPRESSED
    inner = inflate_ttx(data) if compressed else data
    if inner[:8] != MAGIC_PLAIN:
        raise TtxError("not a TTX texture container after inflate")
    info = parse_ttx(inner)
    rgba = decode_rgba(info)
    if flip:
        rgba = flip_vertical(rgba, info["width"], info["height"])
    return {
        "width": info["width"],
        "height": info["height"],
        "format": info["format"],
        "mips": info["mips"],
        "compressed": compressed,
        "po2": _is_po2(info["width"]) and _is_po2(info["height"]),
        "rgba": rgba,
    }


def ttx_to_png(
    in_path: str,
    out_path: str,
    flip: bool = False,
    status=None,
) -> dict:
    """Convert a .ttx file to .png. ``status`` is an optional callable(str)."""
    if status:
        status(f"Reading {os.path.basename(in_path)} ...")
    with open(in_path, "rb") as f:
        raw = f.read()
    if status:
        status("Decoding ...")
    result = decode(raw, flip=flip)
    if status:
        if not result["po2"]:
            status(_po2_warning(result["width"], result["height"]))
        status("Writing PNG ...")
    _save_png(out_path, result["rgba"], result["width"], result["height"])
    if status:
        status("Done.")
    return result


def _save_png(path: str, rgba: bytes, w: int, h: int) -> None:
    try:
        from PIL import Image
    except ImportError:
        linetext = (
            "PNG output needs the 'Pillow' package. Install it with:  pip install Pillow"
        )
        raise TtxError(linetext)
    img = Image.frombytes("RGBA", (w, h), bytes(rgba))
    img.save(path, "PNG")


# ---------------------------------------------------------------------------
# PNG -> TTX (encode)
# ---------------------------------------------------------------------------

ENCODABLE_FORMATS = {
    "type_rgba": "RGBA (lossless)",
    "type_r": "Grayscale R8",
    "type_rgb_s3tc_dxt1": "DXT1 (BC1, no alpha)",
    "type_rgba_s3tc_dxt5": "DXT5 (BC3, alpha)",
}


def encode_png(
    in_path: str,
    out_path: str,
    fmt: str = "type_rgba",
    flip: bool = False,
    status=None,
) -> dict:
    """Encode a PNG/JPG image to a plain (uncompressed) .ttx container."""
    if fmt not in ENCODABLE_FORMATS:
        raise TtxError(f"unsupported output format: {fmt}")
    try:
        from PIL import Image
    except ImportError:
        raise TtxError(
            "PNG encode needs the 'Pillow' package. Install it with:  pip install Pillow"
        )
    if status:
        status(f"Reading {os.path.basename(in_path)} ...")
    img = Image.open(in_path).convert("RGBA")
    if flip:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    w, h = img.size
    if status:
        status(f"Encoding {fmt} ...")
        if not (_is_po2(w) and _is_po2(h)):
            status(_po2_warning(w, h))
    if fmt == "type_rgba":
        payload = img.tobytes()
    elif fmt == "type_r":
        payload = img.convert("L").tobytes()
    elif fmt == "type_rgb_s3tc_dxt1":
        payload = _encode_bc1(img)
    elif fmt == "type_rgba_s3tc_dxt5":
        payload = _encode_bc3(img)
    else:
        raise TtxError(f"unsupported output format: {fmt}")
    data = _build_plain_container(fmt, w, h, payload)
    if status:
        status("Writing TTX ...")
    with open(out_path, "wb") as f:
        f.write(data)
    if status:
        status("Done.")
    return {"width": w, "height": h, "format": fmt, "mips": 1,
            "compressed": False, "po2": _is_po2(w) and _is_po2(h)}


def _u64_bytes(v: int) -> bytes:
    return v.to_bytes(8, "little")


def _u32_bytes(v: int) -> bytes:
    return v.to_bytes(4, "little")


def _prop_chunk(payload: bytes) -> bytes:
    sz = 32 + len(payload)
    return b"\x00" * 16 + _u64_bytes(sz) + _u64_bytes(sz) + payload


def _str_chunk(name: str) -> bytes:
    b = name.encode("ascii")
    return _prop_chunk(_u64_bytes(len(b)) + b)


def _data_chunk(payload: bytes) -> bytes:
    return _prop_chunk(payload)


def _build_plain_container(fmt: str, w: int, h: int, payload: bytes) -> bytes:
    props = (
        _str_chunk(fmt)
        + _str_chunk("target_2d")
        + _prop_chunk(_u32_bytes(w))
        + _prop_chunk(_u32_bytes(h))
        + _prop_chunk(_u32_bytes(1))
        + _prop_chunk(_u32_bytes(1))
        + _data_chunk(payload)
    )
    container = MAGIC_PLAIN + _u64_bytes(0) + _u64_bytes(0) + _u64_bytes(32)
    container += props
    container = container[:16] + _u64_bytes(len(container)) + container[24:]
    return container


# --- BC1 / BC3 block compression ------------------------------------------

def _rgb565(c) -> int:
    return ((c[0] & 0xF8) << 8) | ((c[1] & 0xFC) << 3) | (c[2] >> 3)


def _rgb_from565(v: int):
    return [
        ((v >> 11) & 0x1F) * 255 // 31,
        ((v >> 5) & 0x3F) * 255 // 63,
        (v & 0x1F) * 255 // 31,
    ]


def _extreme_pairs(pix):
    best = (None, None)
    best_d = -1
    n = len(pix)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            d = 0
            a = pix[i]
            b = pix[j]
            for k in range(3):
                diff = a[k] - b[k]
                d += diff * diff
            if d > best_d:
                best_d = d
                best = (i, j)
    return pix[best[0]], pix[best[1]]


def _dist3(a, b):
    d = 0
    for k in range(3):
        diff = a[k] - b[k]
        d += diff * diff
    return d


def _encode_bc1_block(pixels, transparent: bool) -> bytes:
    c0, c1 = _extreme_pairs(pixels)
    cfg0 = _rgb565(c0)
    cfg1 = _rgb565(c1)
    if transparent:
        if cfg0 > cfg1:
            cfg0, cfg1 = cfg1, cfg0
            c0, c1 = c1, c0
    else:
        if cfg0 <= cfg1:
            cfg0, cfg1 = cfg1, cfg0
            c0, c1 = c1, c0
            if cfg0 == cfg1:
                cfg0 = (cfg0 + 1) & 0xFFFF
    ca = _rgb_from565(cfg0)
    cb = _rgb_from565(cfg1)
    if transparent:
        c2 = [(ca[k] + cb[k]) // 2 for k in range(3)]
        c3 = [0, 0, 0]
    else:
        c2 = [(2 * ca[k] + cb[k]) // 3 for k in range(3)]
        c3 = [(ca[k] + 2 * cb[k]) // 3 for k in range(3)]
    palette = (ca, cb, c2, c3)
    indices = 0
    for i in range(16):
        best = 0
        best_d = 1 << 30
        p = pixels[i]
        if transparent and p[3] < 128:
            best = 3
        else:
            for idx in range(4):
                d = _dist3(p, palette[idx])
                if d < best_d:
                    best_d = d
                    best = idx
        indices |= best << (2 * i)
    return bytes([cfg0 & 0xFF, cfg0 >> 8, cfg1 & 0xFF, cfg1 >> 8,
                  indices & 0xFF, (indices >> 8) & 0xFF,
                  (indices >> 16) & 0xFF, (indices >> 24) & 0xFF])


_ALPHA7 = [6, 5, 4, 3, 2, 1, 0]
_ALPHA5 = [4, 3, 2, 1, 0]


def _encode_bc3_block(pixels) -> bytes:
    alphas = [p[3] for p in pixels]
    a0 = max(alphas)
    a1 = min(alphas)
    if a0 == a1:
        a0 = 255
        a1 = 0
    if a0 > a1:
        pal = [a0, a1]
        for m in _ALPHA7:
            pal.append((m * a0 + (6 - m) * a1) // 7)
    else:
        pal = [a0, a1]
        for m in _ALPHA5:
            pal.append((m * a0 + (4 - m) * a1) // 5)
        pal.append(0)
        pal.append(255)
    apacked = 0
    for i in range(16):
        a = alphas[i]
        best = 0
        best_d = 1 << 30
        for idx, v in enumerate(pal):
            d = (a - v) * (a - v)
            if d < best_d:
                best_d = d
                best = idx
        apacked |= best << (3 * i)
    abits = bytearray(8)
    abits[0] = a0
    abits[1] = a1
    for b in range(6):
        abits[2 + b] = (apacked >> (8 * b)) & 0xFF
    color_block = _encode_bc1_block(pixels, transparent=False)
    return bytes(abits) + color_block


def _encode_bc1(img) -> bytes:
    w, h = img.size
    rgba = img.tobytes()
    bw = (w + 3) // 4
    bh = (h + 3) // 4
    out = bytearray()
    for by in range(bh):
        for bx in range(bw):
            pixels = []
            transparent = False
            for yy in range(4):
                y = by * 4 + yy
                if y >= h:
                    y = h - 1
                for xx in range(4):
                    x = bx * 4 + xx
                    if x >= w:
                        x = w - 1
                    off = (y * w + x) * 4
                    px = (rgba[off], rgba[off + 1], rgba[off + 2], rgba[off + 3])
                    pixels.append(px)
                    if px[3] < 128:
                        transparent = True
            out += _encode_bc1_block(pixels, transparent)
    return bytes(out)


def _encode_bc3(img) -> bytes:
    w, h = img.size
    rgba = img.tobytes()
    bw = (w + 3) // 4
    bh = (h + 3) // 4
    out = bytearray()
    for by in range(bh):
        for bx in range(bw):
            pixels = []
            for yy in range(4):
                y = by * 4 + yy
                if y >= h:
                    y = h - 1
                for xx in range(4):
                    x = bx * 4 + xx
                    if x >= w:
                        x = w - 1
                    off = (y * w + x) * 4
                    pixels.append((rgba[off], rgba[off + 1], rgba[off + 2], rgba[off + 3]))
            out += _encode_bc3_block(pixels)
    return bytes(out)


def _auto_cli(argv=None):
    """CLI by file extension:
      .ttx        -> PNG         python ttx_converter.py in.ttx [-o out.png] [--flip]
      .png/.jpg   -> .ttx        python ttx_converter.py in.png -t [--format type_rgba]
      .tsb        -> .wav        python ttx_converter.py in.tsb [-o out.wav]
      .wav        -> .tsb        python ttx_converter.py in.wav [-o out.tsb]
      .mp3/.flac/.ogg -> .wav    python ttx_converter.py in.mp3 [-o out.wav]
      .toc/.tsc/.wad/.tmb/.tsl -> .txt  python ttx_converter.py in.toc [-o out.txt]"""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        import argparse

        p = argparse.ArgumentParser(
            description="Convert Aerofly FS .ttx/.tsb/compressed container files and audio"
        )
        p.add_argument("paths", nargs="+",
                       help=".ttx/.png/.tsb/.toc/.tsc/.wad/.tmb/.tsl/.wav/.mp3/.flac/.ogg "
                            "file(s) or folder(s)")
        p.add_argument("-o", "--output", help="Output file name (single file only)")
        p.add_argument("-t", "--to-ttx", action="store_true",
                       help="Encode PNG/JPG -> .ttx instead of decoding")
        p.add_argument("-f", "--format", default="type_rgba",
                       choices=sorted(ENCODABLE_FORMATS),
                       help="Output texture format when encoding")
        p.add_argument("--flip", action="store_true",
                       help="Flip vertically (for liveries)")
        p.add_argument("--info", action="store_true", help="Print info only")
        args = p.parse_args(argv)
    except ImportError:
        args = None

    import fnmatch
    from pathlib import Path

    DEFAULT_PATS = (
        "*.ttx", "*.tsb", "*.toc", "*.tsc", "*.wad", "*.tmb", "*.tsl",
        "*.wav", "*.mp3", "*.flac", "*.ogg",
    )
    EXT_PATTERN = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tga")
    files = []
    for pt in args.paths:
        if os.path.isdir(pt):
            pats = EXT_PATTERN if args.to_ttx else DEFAULT_PATS
            files.extend(
                str(x)
                for x in Path(pt).rglob("*")
                if x.is_file()
                and any(fnmatch.fnmatch(x.name.lower(), pat) for pat in pats)
            )
        else:
            files.append(pt)

    if not files:
        print("No matching files found.")
        return 1

    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f}")
        if args.output and i > 1:
            args.output = None
        low = f.lower()
        try:
            if low.endswith((".mp3", ".flac", ".ogg")):
                from audio_utils import audio_to_wav

                out = args.output or (os.path.splitext(f)[0] + ".wav")
                info = audio_to_wav(f, out,
                                    status=lambda msg: print(f"    {msg}"))
                if args.info:
                    print(f"    {info['source']}  {info['sample_rate']:.0f} Hz "
                          f"{info['channels']}ch  "
                          f"{info['frames']} frames  {info['bits']}-bit WAV")
                continue
            if low.endswith(".wav"):
                from tsb_decoder import wav_to_tsb

                out = args.output or (os.path.splitext(f)[0] + ".tsb")
                info = wav_to_tsb(f, out,
                                  status=lambda msg: print(f"    {msg}"))
                if args.info:
                    print(f"    {info['format']} {info['sample_rate']:.0f} Hz "
                          f"{info['channels']}ch {info['bits']}-bit {info['frames']} frames")
                continue
            if low.endswith(".tsb"):
                from tsb_decoder import tsb_to_wav

                out = args.output or (os.path.splitext(f)[0] + ".wav")
                info = tsb_to_wav(f, out,
                                  status=lambda msg: print(f"    {msg}"))
                if args.info:
                    print(f"    {info['format']} {info['sample_rate']:.0f} Hz "
                          f"{info['channels']}ch {info['bits']}-bit")
                continue
            if low.endswith((".toc", ".tsc", ".wad", ".tmb", ".tsl")):
                from toc_decoder import toc_to_txt

                out = args.output or (f + ".txt")
                doc = toc_to_txt(f, out,
                                 status=lambda msg: print(f"    {msg}"))
                print(f"    {doc['variant']} placement_count={doc['placement_count']}")
                continue
            if (args.to_ttx or not low.endswith(".ttx")):
                if len(files) == 1 and args.output:
                    out = args.output
                else:
                    out = os.path.splitext(f)[0] + ".ttx"
                encode_png(f, out, fmt=args.format, flip=args.flip,
                           status=lambda msg, f=f: print(f"    {msg}"))
                continue
            with open(f, "rb") as fh:
                raw = fh.read()
            res = decode(raw, flip=args.flip)
            if not res["po2"]:
                print(f"    {_po2_warning(res['width'], res['height'])}")
            if args.info:
                print(
                    f"    {res['format']} {res['width']}x{res['height']} "
                    f"mips={res['mips']} compressed={res['compressed']}"
                )
                continue
            if len(files) == 1 and args.output:
                out = args.output
            else:
                out = os.path.splitext(f)[0] + ".png"
            _save_png(out, res["rgba"], res["width"], res["height"])
            print(f"    -> {out}")
        except Exception as exc:
            print(f"    ERROR: {exc}")
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(_auto_cli())
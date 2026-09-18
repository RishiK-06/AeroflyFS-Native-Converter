from __future__ import annotations

import json
import os
import struct

from ttx_converter import TtxError, _skip_containers, _u64, inflate_ttx

MAGIC_TOC = bytes([0xCD, 0x7D, 0x1C, 0x0B, 0x54, 0xDE, 0x0F, 0xE1])

TYPE_STRING = bytes([0x9D, 0xDB, 0x2D, 0x4B, 0x68, 0xAC, 0xD1, 0xBD])
TYPE_V3 = bytes([0x25, 0x34, 0xC2, 0xA4, 0xD3, 0xA2, 0x43, 0xA3])
TYPE_LIST = bytes([0x78, 0xAE, 0xAC, 0xE3, 0xB8, 0x01, 0xB4, 0x27])


def _f32(b: bytes, off: int) -> float:
    return struct.unpack_from("<f", b, off)[0]


def _f64(b: bytes, off: int) -> float:
    return struct.unpack_from("<d", b, off)[0]


def _prefix_eq(data: bytes, off: int, prefix: bytes) -> bool:
    return data[off : off + 8] == prefix


def _read_string_at(data, off):
    if off + 32 > len(data) or not _prefix_eq(data, off, TYPE_STRING):
        return None
    size = _u64(data, off + 16)
    hs = _u64(data, off + 24)
    if size < 40 or size != hs or off + size > len(data):
        return None
    n = _u64(data, off + 32)
    if n < 0 or n > 512 or 40 + n > size:
        return None
    raw = data[off + 40 : off + 40 + n]
    try:
        return {"text": raw.decode("ascii"), "next": off + size}
    except UnicodeDecodeError:
        return None


def _read_v3_at(data, off):
    if off + 56 > len(data) or not _prefix_eq(data, off, TYPE_V3):
        return None
    size = _u64(data, off + 16)
    hs = _u64(data, off + 24)
    if size != 56 or hs != 56:
        return None
    return {
        "lon": _f64(data, off + 32),
        "lat": _f64(data, off + 40),
        "alt": _f64(data, off + 48),
        "next": off + 56,
    }


def _read_f32_prop(data, off):
    if off + 40 > len(data):
        return None
    size = _u64(data, off + 16)
    hs = _u64(data, off + 24)
    if size != 36 or hs != 40:
        return None
    return {"value": _f32(data, off + 32), "next": off + 40}


def _parse_placement_block(data, start, end):
    off = start
    name = None
    while off + 32 <= end:
        got = _read_string_at(data, off)
        if got:
            name = got["text"]
            off = got["next"]
            break
        size = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        step = 40 if (size == 36 and hs == 40) else int(size)
        if step < 32 or off + step > end:
            break
        off += step
    if name is None:
        return None
    v3 = _read_v3_at(data, off)
    if v3 is None:
        return {"name": name}
    off = v3["next"]
    direction = None
    scale_factor = None
    v1 = _read_f32_prop(data, off)
    if v1:
        direction = v1["value"]
        off = v1["next"]
        v2 = _read_f32_prop(data, off)
        if v2:
            scale_factor = v2["value"]
    out = {"name": name, "longitude": v3["lon"], "latitude": v3["lat"], "altitude": v3["alt"]}
    if direction is not None:
        out["direction"] = direction
    if scale_factor is not None:
        out["scale_factor"] = scale_factor
    return out


def _walk_list_placements(data, list_off):
    size = _u64(data, list_off + 16)
    end = list_off + size
    off = list_off + 32
    placements = []
    while off + 32 <= end:
        csize = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        if csize < 32 or off + csize > end:
            break
        if _prefix_eq(data, off, TYPE_LIST) and hs == 32:
            block = _parse_placement_block(data, off + 32, off + csize)
            if block:
                placements.append(block)
            off += csize
            continue
        block = _parse_placement_block(data, off, off + csize)
        if block and "longitude" in block:
            placements.append(block)
            off += csize
            continue
        off += 40 if (csize == 36 and hs == 40) else csize
    return placements


def _find_coordinate_system(data):
    off = _skip_containers(data)
    end = min(len(data), off + 0x200)
    while off + 48 <= end:
        got = _read_string_at(data, off)
        if got:
            return got["text"]
        size = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        step = 40 if (size == 36 and hs == 40) else int(size)
        if step < 32:
            break
        off += step
    return None


def parse_toc(data: bytes, compressed: bool = False) -> dict:
    """Parse a plain / inflated TOC blob into a summary dict."""
    if data[:8] != MAGIC_TOC:
        raise TtxError(
            "not a TOC container (magic %s)" % data[:8].hex()
        )
    coordinate_system = _find_coordinate_system(data) or "lonlat"
    placements: list = []

    for i in range(len(data) - 31):
        if _prefix_eq(data, i, TYPE_LIST) and _u64(data, i + 24) == 32:
            size = _u64(data, i + 16)
            if size > 200:
                placements = _walk_list_placements(data, i)
                if placements:
                    break

    if not placements:
        i = 0
        while i + 48 <= len(data):
            got = _read_string_at(data, i)
            if not got:
                i += 1
                continue
            if got["text"] == "lonlat":
                i = got["next"]
                continue
            v3 = _read_v3_at(data, got["next"])
            if not v3:
                i = got["next"]
                continue
            off = v3["next"]
            direction = None
            scale_factor = None
            v1 = _read_f32_prop(data, off)
            if v1:
                direction = v1["value"]
                off = v1["next"]
                v2 = _read_f32_prop(data, off)
                if v2:
                    scale_factor = v2["value"]
                    off = v2["next"]
            entry = {
                "name": got["text"],
                "longitude": v3["lon"],
                "latitude": v3["lat"],
                "altitude": v3["alt"],
            }
            if direction is not None:
                entry["direction"] = direction
            if scale_factor is not None:
                entry["scale_factor"] = scale_factor
            placements.append(entry)
            i = off

    return {
        "kind": "toc",
        "variant": "cultivation_xref" if placements else "summary_only",
        "compressed": compressed,
        "inflated_bytes": len(data),
        "coordinate_system": coordinate_system,
        "buildings_texture_folder": "",
        "placement_count": len(placements),
        **({"xref_list": placements} if placements else {}),
    }


def _fmt_tm_number(x: float, is_f32: bool = False) -> str:
    if is_f32:
        x = struct.unpack("<f", struct.pack("<f", x))[0]
    if float(x).is_integer() and abs(x) < 1e15:
        return str(int(x))
    s = f"{x:.12f}".rstrip("0").rstrip(".")
    return s


def emit_toc_text(doc: dict) -> str:
    xrefs = doc.get("xref_list")
    if doc.get("variant") == "summary_only" or not xrefs:
        raise TtxError(
            "this TOC has no xref_list (likely a cultivation tile). "
            "Use JSON download for a summary."
        )
    coord = doc.get("coordinate_system") or "lonlat"
    lines = [
        "<[file][][]",
        "    <[cultivation][][]",
        f"        <[string8u][coordinate_system][{coord}]>",
        "        <[string8][buildings_texture_folder][]>",
        "        <[list_plant][plant_list][]",
        "        >",
        "        <[plant_collections][plant_collection_list][]",
        "            <[uint32][num_plants][0]>",
        "            <[list_uint8][plants_raw_data][]>",
        "            <[list_plant_collection][plant_collections][]",
        "            >",
        "        >",
        "        <[list_building_shaped][building_shaped_list][]",
        "        >",
        "        <[list_building_complex][building_complex_list][]",
        "        >",
        "        <[list_light][light_list][]",
        "        >",
        "        <[list_lightc_group][lightc_group_list][]",
        "        >",
        "        <[list_airport_light][airport_light_list][]",
        "        >",
        "        <[list_generic_object][generic_object_list][]",
        "        >",
        "        <[list_power_line][power_lines][]",
        "        >",
        "        <[list_xref][xref_list][]",
    ]
    for i, obj in enumerate(xrefs):
        lon = _fmt_tm_number(obj["longitude"])
        lat = _fmt_tm_number(obj["latitude"])
        alt = _fmt_tm_number(obj.get("altitude") or 0)
        direction = _fmt_tm_number(obj.get("direction") or 0, True)
        scale = _fmt_tm_number(obj.get("scale_factor") or obj.get("scale", 1), True)
        lines.extend(
            [
                f"            <[xref][element][{i}]",
                f"                <[string8u][name][{obj['name']}]>",
                f"                <[vector3_float64][position][{lon} {lat} {alt}]>",
                f"                <[float32][direction][{direction}]>",
                f"                <[float32][scale_factor][{scale}]>",
                "            >",
            ]
        )
    lines.extend(["        >", "    >", ">", ""])
    return "\n".join(lines)


def toc_to_json(in_path: str, out_path: str, status=None) -> dict:
    """Convert a .toc file to .toc.json (+ .toc.txt when placements exist)."""
    if status:
        status(f"Reading {in_path} ...")
    with open(in_path, "rb") as fh:
        raw = fh.read()
    if status:
        status("Decoding ...")
    doc = parse_toc(inflate_ttx(raw), compressed=raw[:8] != MAGIC_TOC)
    try:
        text = emit_toc_text(doc)
    except TtxError:
        text = None
    if status:
        status("Writing JSON ...")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    if text is not None:
        txt_path = os.path.splitext(out_path)[0] + ".txt"
        if status:
            status(f"Writing {os.path.basename(txt_path)} ...")
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    if status:
        status("Done.")
    return doc
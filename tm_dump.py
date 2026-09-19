from __future__ import annotations

import argparse
import os
import struct
import sys

from tm_ids import NAME_IDS, TYPE_NAMES
from ttx_converter import TtxError as TmError, _u64, inflate_ttx as inflate_tm

HEX_BLOB_LINE = 32
MAX_INLINE_BLOB = 64
LIST_PREFIXES = ("pointer_list_", "list_", "array_")


def _hex_id(b: bytes) -> str:
    return b.hex()


def _label(table: dict, raw: bytes, prefix: str) -> str:
    key = _hex_id(raw)
    if key in table:
        return table[key]
    return prefix + key[:8]


def _step(size: int, hs: int) -> int:
    return max(int(size), int(hs), 32)


def _f32(b: bytes, off: int = 0) -> float:
    return struct.unpack_from("<f", b, off)[0]


def _f64(b: bytes, off: int = 0) -> float:
    return struct.unpack_from("<d", b, off)[0]


def _fmt_num(x: float, is_f32: bool = False) -> str:
    if is_f32:
        x = struct.unpack("<f", struct.pack("<f", x))[0]
    if float(x).is_integer() and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.15g}"


def _item_type(parent_type: str) -> str:
    for prefix in LIST_PREFIXES:
        if parent_type.startswith(prefix):
            return parent_type[len(prefix) :]
    return "element"


def _looks_like_string(payload: bytes) -> str | None:
    if len(payload) < 8:
        return None
    n = _u64(payload, 0)
    if n < 0 or n > 1_000_000 or 8 + n > len(payload):
        return None
    raw = payload[8 : 8 + n]
    if n == 0:
        return ""
    if not all(32 <= b < 127 or b in (9, 10, 13) for b in raw):
        return None
    return raw.decode("ascii", errors="replace")


def _promote_type(type_name: str, payload: bytes) -> str:
    if type_name == "float32" and len(payload) > 4 and len(payload) % 4 == 0:
        return "list_float32"
    if type_name == "uint32" and len(payload) > 4 and len(payload) % 4 == 0:
        return "list_uint32"
    if type_name == "int32" and len(payload) > 4 and len(payload) % 4 == 0:
        return "array_int32"
    if type_name == "float64" and len(payload) > 8 and len(payload) % 8 == 0:
        return "list_float64"
    if type_name == "list_uint8" and len(payload) == 1:
        return "uint8"
    return type_name


def _fmt_blob(payload: bytes) -> tuple[str, list[str] | None]:
    if not payload:
        return "", None
    if len(payload) <= MAX_INLINE_BLOB:
        return payload.hex(), None
    rows = [
        payload[i : i + HEX_BLOB_LINE].hex()
        for i in range(0, len(payload), HEX_BLOB_LINE)
    ]
    return str(len(payload)), rows


def _leaf_value(type_name: str, payload: bytes) -> tuple[str, list[str] | None]:
    if type_name == "bool":
        v = payload[0] if payload else 0
        return ("true" if v else "false"), None
    if type_name.startswith("string"):
        text = _looks_like_string(payload)
        return ("" if text is None else text), None
    if type_name == "float32" and len(payload) >= 4:
        return _fmt_num(_f32(payload), True), None
    if type_name == "float64" and len(payload) >= 8:
        return _fmt_num(_f64(payload), False), None
    if type_name == "int8" and payload:
        return str(struct.unpack_from("<b", payload, 0)[0]), None
    if type_name == "uint8" and payload:
        return str(payload[0]), None
    if type_name == "uint16" and len(payload) >= 2:
        return str(struct.unpack_from("<H", payload, 0)[0]), None
    if type_name == "int32" and len(payload) >= 4:
        return str(struct.unpack_from("<i", payload, 0)[0]), None
    if type_name == "uint32" and len(payload) >= 4:
        return str(struct.unpack_from("<I", payload, 0)[0]), None
    if type_name == "uint64" and len(payload) >= 8:
        return str(struct.unpack_from("<Q", payload, 0)[0]), None
    if type_name == "vector2_float64" and len(payload) >= 16:
        return " ".join(_fmt_num(_f64(payload, i)) for i in range(0, 16, 8)), None
    if type_name == "vector3_float64" and len(payload) >= 24:
        return " ".join(_fmt_num(_f64(payload, i)) for i in range(0, 24, 8)), None
    if type_name == "vector4_float32" and len(payload) >= 16:
        return " ".join(_fmt_num(_f32(payload, i), True) for i in range(0, 16, 4)), None
    if type_name in ("list_float32", "raw_f32") and len(payload) >= 4:
        vals = [_fmt_num(_f32(payload, i), True) for i in range(0, len(payload) // 4 * 4, 4)]
        return " ".join(vals), None
    if type_name == "list_float64" and len(payload) >= 8:
        vals = [_fmt_num(_f64(payload, i)) for i in range(0, len(payload) // 8 * 8, 8)]
        return " ".join(vals), None
    if type_name in ("list_uint32",) and len(payload) >= 4:
        vals = [str(struct.unpack_from("<I", payload, i)[0]) for i in range(0, len(payload) // 4 * 4, 4)]
        return " ".join(vals), None
    if type_name == "array_int32" and len(payload) >= 4:
        vals = [str(struct.unpack_from("<i", payload, i)[0]) for i in range(0, len(payload) // 4 * 4, 4)]
        return " ".join(vals), None
    if type_name == "list_vector3_float32" and len(payload) >= 12:
        vals = [_fmt_num(_f32(payload, i), True) for i in range(0, len(payload) // 4 * 4, 4)]
        return " ".join(vals), None
    if type_name == "matrix4_float64" and len(payload) >= 128:
        vals = [_fmt_num(_f64(payload, i)) for i in range(0, 128, 8)]
        return " ".join(vals), None
    if type_name == "list_uint8":
        if len(payload) <= 1:
            return str(payload[0] if payload else 0), None
        return _fmt_blob(payload)

    text = _looks_like_string(payload)
    if text is not None:
        return text, None
    if len(payload) == 1:
        return str(payload[0]), None
    if len(payload) == 4:
        return _fmt_num(_f32(payload), True), None
    if len(payload) == 8:
        return _fmt_num(_f64(payload), False), None
    if payload and len(payload) % 8 == 0 and len(payload) <= 128:
        return " ".join(_fmt_num(_f64(payload, i)) for i in range(0, len(payload), 8)), None
    if payload and len(payload) % 4 == 0 and len(payload) <= 64:
        return " ".join(_fmt_num(_f32(payload, i), True) for i in range(0, len(payload), 4)), None
    return _fmt_blob(payload)


def _emit_node(
    data: bytes,
    start: int,
    end: int,
    indent: int,
    parent_typ: bytes | None,
    parent_nam: bytes | None,
) -> list[str]:
    lines: list[str] = []
    off = start
    pad = " " * indent
    item_index = 0
    while off + 32 <= end:
        typ = data[off : off + 8]
        nam = data[off + 8 : off + 16]
        size = _u64(data, off + 16)
        hs = _u64(data, off + 24)
        step = _step(size, hs)
        if off + step > end:
            if int(size) >= 32 and off + int(size) <= end:
                step = int(size)
            else:
                lines.append(f"{pad}// truncated object at 0x{off:x} size={size} hs={hs}")
                break
        payload_len = max(0, int(size) - 32)
        payload = data[off + 32 : off + 32 + min(payload_len, step - 32)]
        type_name = _label(TYPE_NAMES, typ, "type_")
        field_name = _label(NAME_IDS, nam, "name_")
        is_list_item = (
            parent_typ is not None
            and parent_nam is not None
            and typ == parent_typ
            and nam == parent_nam
        )
        if is_list_item:
            parent_label = _label(TYPE_NAMES, parent_typ, "type_")
            type_name = _item_type(parent_label)
            field_name = "element"

        type_name = _promote_type(type_name, payload)
        if hs == 32 and not is_list_item and type_name in ("uint32", "uint8", "float32"):
            type_name = "list_" + type_name

        if hs == 32:
            value = str(item_index) if is_list_item else ""
            if is_list_item:
                item_index += 1
            lines.append(f"{pad}<[{type_name}][{field_name}][{value}]")
            lines.extend(_emit_node(data, off + 32, off + step, indent + 4, typ, nam))
            lines.append(f"{pad}>")
        else:
            value, extra = _leaf_value(type_name, payload)
            if extra is None:
                lines.append(f"{pad}<[{type_name}][{field_name}][{value}]>")
            else:
                lines.append(f"{pad}<[{type_name}][{field_name}][{value}]")
                extra_pad = " " * (indent + 4)
                for row in extra:
                    lines.append(f"{extra_pad}{row}")
                lines.append(f"{pad}>")
        off += step
    return lines


def dump_tm_text(data: bytes, wrap_file: bool = True) -> str:
    blob = inflate_tm(data)
    if len(blob) < 32:
        raise TmError("inflated blob is too small to be a TM object")
    root_indent = 4 if wrap_file else 0
    root_lines = _emit_node(blob, 0, len(blob), root_indent, None, None)
    if wrap_file:
        lines = ["<[file][][]", *root_lines, ">", ""]
    else:
        lines = [*root_lines, ""]
    return "\n".join(lines)


def dump_path(in_path: str, out_path: str | None = None) -> str:
    with open(in_path, "rb") as fh:
        raw = fh.read()
    text = dump_tm_text(raw)
    if out_path is None:
        out_path = in_path + ".decoded.txt"
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Inflate Aerofly TM containers (.toc/.tsc/.wad/.tmb/.tsl) and dump them as text."
    )
    p.add_argument("inputs", nargs="+", help="Input file(s)")
    p.add_argument("-o", "--output", help="Output .txt (only valid with a single input)")
    p.add_argument("--no-file-wrap", action="store_true", help="Do not wrap the dump in <[file][][]>")
    args = p.parse_args(argv)
    if args.output and len(args.inputs) != 1:
        p.error("--output requires exactly one input file")
    for path in args.inputs:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = dump_tm_text(raw, wrap_file=not args.no_file_wrap)
        out = args.output if args.output else path + ".decoded.txt"
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"Wrote {out} ({len(text)} chars, inflated {len(inflate_tm(raw))} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

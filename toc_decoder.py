from __future__ import annotations

import os
import re

from tm_dump import dump_tm_text
from ttx_converter import MAGIC_COMPRESSED, TtxError, inflate_ttx

XREF_RE = re.compile(r"<\[xref\]\[element\]\[")

TM_EXTENSIONS = (".toc", ".tsc", ".wad", ".tmb", ".tsl")


def parse_toc(data: bytes, compressed: bool = False) -> dict:
    """Inflate a TM blob and emit a generic Aerofly text tree (generic text)."""
    inner = inflate_ttx(data)
    text = dump_tm_text(data)
    xref_count = len(XREF_RE.findall(text))
    return {
        "kind": "tm",
        "variant": "generic_text",
        "compressed": compressed or data[:8] == MAGIC_COMPRESSED,
        "inflated_bytes": len(inner),
        "placement_count": xref_count,
        "text": text,
    }


def emit_toc_text(doc: dict) -> str:
    text = doc.get("text")
    if not text:
        raise TtxError("no TM text in document")
    return text


def toc_to_txt(in_path: str, out_path: str, status=None) -> dict:
    """Convert a TM container (.toc/.tsc/.wad/.tmb/.tsl) to a generic .txt tree.

    Compatible with AeroflyFS-Native-Converter CLI/GUI: *out_path* is the
    ``.txt`` path that receives the full generic TM text dump.
    """
    if status:
        status(f"Reading {in_path} ...")
    with open(in_path, "rb") as fh:
        raw = fh.read()
    if status:
        status("Decoding ...")
    doc = parse_toc(raw, compressed=raw[:8] == MAGIC_COMPRESSED)
    text = emit_toc_text(doc)
    if status:
        status(f"Writing {os.path.basename(out_path)} ...")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if status:
        status("Done.")
    return doc
from __future__ import annotations

import json
import os
import re

from tm_dump import dump_tm_text
from ttx_converter import MAGIC_COMPRESSED, TtxError, inflate_ttx

XREF_RE = re.compile(r"<\[xref\]\[element\]\[")

TM_EXTENSIONS = (".toc", ".tsc", ".wad", ".tmb", ".tsl")


def parse_toc(data: bytes, compressed: bool = False) -> dict:
    """Inflate a TM blob and emit a generic Aerofly text tree (not xref-only JSON)."""
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


def toc_to_json(in_path: str, out_path: str, status=None) -> dict:
    """Convert a TM container to JSON summary + sibling .txt tree.

    Compatible with AeroflyFS-Native-Converter CLI/GUI: *out_path* is the
    ``.json`` path; the full TM text is written next to it as ``.txt``.
    """
    if status:
        status(f"Reading {in_path} ...")
    with open(in_path, "rb") as fh:
        raw = fh.read()
    if status:
        status("Decoding ...")
    doc = parse_toc(raw, compressed=raw[:8] == MAGIC_COMPRESSED)
    text = emit_toc_text(doc)
    summary = {k: v for k, v in doc.items() if k != "text"}
    if status:
        status("Writing JSON ...")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    txt_path = os.path.splitext(out_path)[0] + ".txt"
    if status:
        status(f"Writing {os.path.basename(txt_path)} ...")
    with open(txt_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if status:
        status("Done.")
    return doc


def toc_to_txt(in_path: str, out_path: str, status=None) -> dict:
    """Convert a TM container to a generic Aerofly text tree (``out_path``)."""
    if status:
        status(f"Reading {in_path} ...")
    with open(in_path, "rb") as fh:
        raw = fh.read()
    if status:
        status("Decoding ...")
    doc = parse_toc(raw, compressed=raw[:8] == MAGIC_COMPRESSED)
    text = emit_toc_text(doc)
    if status:
        status("Writing TXT ...")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if status:
        status("Done.")
    return doc

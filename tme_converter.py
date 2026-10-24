"""ZIP <-> TME converter.

.tme is a ZIP wrapper with the folder layout that Aerofly mobile expects
(dlc_aircraft_dr400/aircraft/dr400/european_air_charter/...). It uses
no compression on the inner .ttx files (matching observed .tme format).
"""
from __future__ import annotations

import os
import zipfile
import sys
from pathlib import Path

# The folder tree the mobile loader expects inside .tme
TREE_ROOT = "dlc_aircraft_dr400/aircraft/dr400/european_air_charter"


def zip_to_tme(in_path: str, out_path: str, status=None) -> dict:
    if status:
        status(f"Reading {os.path.basename(in_path)} ...")
    with zipfile.ZipFile(in_path, "r") as zin:
        names = zin.namelist()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                # Remap flat 'european_air_charter/...' into DLC tree
                # Preserve any existing nested paths unchanged.
                fname = info.filename
                if fname.startswith("european_air_charter/"):
                    fname = TREE_ROOT + "/" + fname[len("european_air_charter/"):]
                # If source already uses DLC tree, keep as-is.
                zout.writestr(fname, data)
    if status:
        status("Done.")
    return {"input": in_path, "output": out_path, "mode": "zip_to_tme"}


def tme_to_zip(in_path: str, out_path: str, status=None) -> dict:
    if status:
        status(f"Reading {os.path.basename(in_path)} ...")
    with zipfile.ZipFile(in_path, "r") as zin:
        names = zin.namelist()
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                fname = info.filename
                if fname.startswith(TREE_ROOT + "/"):
                    fname = "european_air_charter/" + fname[len(TREE_ROOT + "/"):]
                zout.writestr(fname, zin.read(info.filename))
    if status:
        status("Done.")
    return {"input": in_path, "output": out_path, "mode": "tme_to_zip"}


def _auto_cli(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        description="Convert ZIP <-> TME (Aerofly mobile DLC wrapper)"
    )
    p.add_argument("paths", nargs="+", help=".tme or .zip file(s) or folder(s)")
    p.add_argument("-o", "--output", help="Output file/dir (single file only)")
    p.add_argument(
        "--to-tme", action="store_true",
        help="ZIP -> TME (default if .tme output requested)"
    )
    p.add_argument(
        "--to-zip", action="store_true",
        help="TME -> ZIP"
    )
    args = p.parse_args(argv)
    if args.to_tme == args.to_zip:
        # Guess from first file extension if ambiguous
        if args.paths:
            first = args.paths[0].lower()
            if first.endswith(".tme"):
                args.to_zip = True
            else:
                args.to_tme = True
    files = []
    for pt in args.paths:
        if os.path.isdir(pt):
            for root, _, names in os.walk(pt):
                for n in names:
                    if n.lower().endswith((".tme", ".zip")):
                        files.append(os.path.join(root, n))
        else:
            files.append(pt)
    if not files:
        print("No .tme / .zip files found.")
        return 1
    ok = 0
    fail = 0
    for i, f in enumerate(files, 1):
        out = args.output or (os.path.splitext(f)[0] + (".tme" if args.to_tme else ".zip"))
        try:
            if args.to_tme:
                zip_to_tme(f, out, status=lambda m: print(f"     {m}"))
            else:
                tme_to_zip(f, out, status=lambda m: print(f"     {m}"))
            print(f"[{i}/{len(files)}] {f} -> {os.path.basename(out)} OK")
            ok += 1
        except Exception as exc:
            print(f"[{i}/{len(files)}] {f} ERROR: {exc}")
            fail += 1
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(_auto_cli())

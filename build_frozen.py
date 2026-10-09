"""Build frozen GUI/CLI binaries with the wasmtime native library bundled.

v1.0.4 of AeroflyFS-Native-Converter: release executables crashed on
LZHAM-compressed .ttx with Failed to load dynlib/dll '_wasmtime.dll'.
PyInstaller must collect the wasmtime package AND copy the platform
native lib into wasmtime/<plat>-<mach>/ next to it.

Usage (from this folder):
    python build_frozen.py
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def wasmtime_add_binary_spec() -> str:
    import wasmtime

    plat = {"linux": "linux", "win32": "win32", "darwin": "darwin"}[sys.platform]
    mach = platform.machine()
    if mach == "AMD64":
        mach = "x86_64"
    if mach in ("arm64", "ARM64"):
        mach = "aarch64"
    lib = {
        "linux": "_libwasmtime.so",
        "win32": "_wasmtime.dll",
        "darwin": "_libwasmtime.dylib",
    }[sys.platform]
    src = Path(wasmtime.__file__).parent / f"{plat}-{mach}" / lib
    if not src.is_file():
        raise SystemExit(f"wasmtime native lib missing: {src}")
    dest = f"wasmtime/{plat}-{mach}"
    return f"{src}{os.pathsep}{dest}"


def _run(args: list[str]) -> None:
    print(" ".join(args), flush=True)
    subprocess.check_call(args, cwd=str(ROOT))


def main() -> int:
    sep = ";" if sys.platform == "win32" else ":"
    wasm_bin = wasmtime_add_binary_spec()
    common = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onefile",
        "--collect-all", "wasmtime",
        "--add-binary", wasm_bin,
        "--add-data", f"tmcompress.wasm{sep}.",
    ]
    assets = ROOT / "assets"
    if assets.is_dir():
        common += ["--add-data", f"assets{sep}assets"]

    gui = ROOT / "ttx_gui_devl.py"
    if not gui.is_file():
        gui = ROOT / "ttx_gui.py"
    if gui.is_file():
        gui_cmd = list(common) + ["--windowed", "--name", "AeroflyFS-Converter", str(gui)]
        ico = ROOT / "assets" / "app_icon.ico"
        if sys.platform == "win32" and ico.is_file():
            gui_cmd[gui_cmd.index("--windowed"):gui_cmd.index("--windowed")] = [
                "--icon", str(ico),
            ]
        _run(gui_cmd)

    cli = ROOT / "ttx_converter.py"
    _run(common + ["--name", "AeroflyFS-Converter-CLI", str(cli)])

    cli_bin = ROOT / "dist" / (
        "AeroflyFS-Converter-CLI.exe" if sys.platform == "win32"
        else "AeroflyFS-Converter-CLI"
    )
    _run([str(cli_bin), "--selftest-wasmtime"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

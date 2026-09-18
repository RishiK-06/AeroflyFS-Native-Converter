# Aerofly FS TTX / TSB / TOC Converter

A Windows / macOS / Linux desktop app that converts **Aerofly FS**
container files and common audio locally:

- `.ttx` textures → **PNG**
- **PNG** → `.ttx` (RGBA8 / R8 / DXT1 / DXT5)
- `.tsb` sounds → **WAV**  and  **WAV** → `.tsb`
- `.mp3`, `.flac`, `.ogg` → **WAV**
- `.toc` scenery tables → **JSON + text**

Built with Python + **PySide6 (Qt 6)** with a dark theme, Runs identically on
Windows, macOS and Linux, Made with inspiration from AuroraBorealis's web convertor (Abflug) which unfortunately went offline.

> **Full setup:** at [INSTALLATION.md](INSTALLATION.md).

## Features

- **Drag & drop** or browse for one or more files (mode picks the accepted type)
- Converts files side-by-side (same folder, matching extension)
- **Flip vertically** option (liveries are stored flipped)
- Handles both plain (`compress_file=false`) and **file-compressed**
  (`compress_file=true`, LZHAM) containers
- Decodes textures: **RGBA8, R8, DXT1 (BC1), DXT3 (BC2), DXT5 (BC3), ETC2,
  ETC2+EAC, ETC1, BC5/RGTC2 (normal maps, Z reconstructed), ASTC**
- Encodes textures: **type_rgba, type_r, type_rgb_s3tc_dxt1, type_rgba_s3tc_dxt5**
- Decodes sounds: mono/stereo N-bit PCM → 16-bit WAV; encodes **WAV → TSB**
- Decodes **MP3/FLAC/OGG → 16-bit WAV** (via `miniaudio`, codecs bundled)
- Decodes TOC: cultivation table with xref placement list → JSON + human-readable text
- GUI extras: conversion types grouped by category, progress bar, live log,
  "Open output folder" after conversion

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python ttx_gui.py      # desktop app
# CLI auto-detects the file type by extension:
python ttx_converter.py <file.ttx> [--flip] [--info]   # texture -> PNG
python ttx_converter.py <file.png>  --to-ttx [--format type_rgba]   # PNG -> TTX
python ttx_converter.py <file.tsb>  [--info]          # sound -> WAV
python ttx_converter.py <file.wav>  [--info]          # WAV -> TSB
python ttx_converter.py <file.mp3>  [--info]          # MP3 (also .flac/.ogg) -> WAV
python ttx_converter.py <file.toc>  [--info]          # table -> JSON + TXT
# CLI also supports folders and multiple files (batch).
```

## Files

| File | Purpose |
|------|---------|
| `ttx_gui.py` | PySide6 app (grouped mode selector, browse + drag-and-drop + batch convert) |
| `ttx_converter.py` | Core TTX parser / decoder / encoder / CLI |
| `tsb_decoder.py` | TSB (sound) container decoder + WAV→TSB encoder |
| `audio_utils.py` | MP3 / FLAC / OGG → WAV (miniaudio) |
| `toc_decoder.py` | TOC (scenery) container decoder → JSON/text |
| `assets/` | App logo (`app_icon.ico`/`.png`) + `make_icon.py` generator |
| `tmcompress.wasm` | LZHAM inflate module (WebAssembly) |
| `INSTALLATION.md` | Step-by-step setup for Windows / macOS / Linux with screenshots |
| `docs/screenshots/` | App screenshots (+ `make_screenshots.py` to regenerate) |
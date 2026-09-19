# Installation Guide — Aerofly FS Converter

Should work normally on **Windows**, **macOS** and **Linux**.

The app window (screen capture of the mode dropdown in the README):



---

## What you need

1. **Python 3.9 or newer** from [python.org](https://www.python.org/downloads/)
   (download the latest 3.12/3.13 installer).
2. An internet connection for one `pip install` command.

The app itself does **not** need internet, ffmpeg, or any system codecs.
MP3 / FLAC / OGG decoding uses the `miniaudio` package (decoders included in the wheel).

---

## Get the app (all platforms)

**Option A — download the ZIP (simplest):**

1. Open <https://github.com/RishiK-06/AeroflyFS-Native-Converter>.
2. Click the green **Code** button → **Download ZIP**.
3. Extract the ZIP anywhere you like. The folder is named
   `AeroflyFS-Native-Converter-main`.

**Option B — clone with git (if you use git):**

```bash
git clone https://github.com/RishiK-06/AeroflyFS-Native-Converter.git
```

Then open a terminal and go into the folder:

```bash
cd AeroflyFS-Native-Converter-main    # ZIP download
# or
cd AeroflyFS-Native-Converter         # git clone
```

All commands below are run from inside this folder.

---

## Windows

### Step 1 — Install Python

1. Download the **Windows installer (64-bit)** from python.org.
2. Run it and **tick "Add python.exe to PATH"** at the bottom of the first page.
3. Click *Install Now*.
4. Open **PowerShell** (Start menu → type `powershell`).

### Step 2 — Install dependencies

```powershell
cd AeroflyFS-Native-Converter-main
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

You should see `Successfully installed PySide6-Essentials ...` (plus Pillow,
wasmtime, texture2ddecoder, miniaudio).

### Step 3 — Run the app

```powershell
python ttx_gui.py
```



---

## macOS

### Step 1 — Install Python

Download the **macOS universal2 installer** from python.org, **or** install via
Homebrew:

```bash
brew install python@3.13
```

### Step 2 — Install dependencies

macOS ships a read-only system Python, so create a virtual environment first:

```bash
cd AeroflyFS-Native-Converter-main
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Your terminal prompt now shows `(venv)`.

### Step 3 — Run the app

```bash
cd AeroflyFS-Native-Converter-main
source venv/bin/activate          # only if the prompt does not show (venv)
python ttx_gui.py
```

If you use **zsh**, you can add a quick alias to `~/.zshrc`:

```bash
alias aerofly-converter='cd ~/AeroflyFS-Native-Converter-main && source ./venv/bin/activate && python ttx_gui.py'
```

### Step 9 — Create a Desktop Launcher

**One-time shortcut creation** — open Terminal and paste this entire block of
commands, then press Enter:

```bash
cat > ~/Desktop/Aerofly\ Converter.command <<'EOF'
#!/bin/bash
cd ~/Downloads/AeroflyFS-Native-Converter-main
source venv/bin/activate
python ttx_gui.py
EOF
chmod +x ~/Desktop/Aerofly\ Converter.command
```

**How to verify:** check your Mac Desktop for a new file named
`Aerofly Converter.command`.



---

## Linux (Debian / Ubuntu / Mint)

**First-time install:**

```bash
sudo apt update && sudo apt install -y python3-pip libxcb-cursor0
cd AeroflyFS-Native-Converter-main
pip3 install --user -r requirements.txt
python3 ttx_gui.py
```



**Notes:**

- `libxcb-cursor0` is only needed for the GUI (the Qt xcb plugin). If you only
  use the command line, skip it.
- If `pip3` complains about an *externally managed environment* (newer distros),
  run the install with the `--break-system-packages` flag instead:

  ```bash
  pip3 install --user --break-system-packages -r requirements.txt
  ```

**Running again later:**

```bash
cd AeroflyFS-Native-Converter-main
python3 ttx_gui.py
```

---

## Using the app

1. Pick a **conversion type** from the drop-down at the top. It is grouped into
   **Textures**, **Audio** and **Scenery**.
2. **Drag & drop** files onto the big dashed area (or click *Browse*).
3. Click **Convert**. Files are written next to the originals; a progress bar and
   a live log show what is happening. When it finishes, **Open output folder**
   appears so you can jump straight to the results.

| Conversion type | Input | Output |
|---|---|---|
| TTX → PNG | `.ttx` texture | `.png` |
| PNG → TTX | `.png`/`.jpg`/`.bmp`/`.tga` | `.ttx` (RGBA, R8, DXT1, DXT5) |
| TSB → WAV | `.tsb` sound | `.wav` (16-bit PCM) |
| WAV → TSB | `.wav` | `.tsb` |
| MP3 → WAV | `.mp3` | `.wav` (16-bit PCM) |
| FLAC → WAV | `.flac` | `.wav` (16-bit PCM) |
| OGG → WAV | `.ogg` | `.wav` (16-bit PCM) |
| Compressed → TXT (generic) | `.toc` / `.tsc` / `.wad` / `.tmb` / `.tsl` | `.txt` |

The same conversions are available from the command line (no GUI). Use `python`
on Windows, `python3` on macOS/Linux:

```bash
python ttx_converter.py <file.ttx> --flip          # texture -> PNG
python ttx_converter.py <file.png> -t --format type_rgba   # PNG -> TTX
python ttx_converter.py <file.tsb>                 # sound -> WAV
python ttx_converter.py <file.wav>                 # WAV -> TSB
python ttx_converter.py <file.mp3>                 # MP3 -> WAV
python ttx_converter.py <file.toc>                 # compressed (.toc/.tsc/.wad/.tmb/.tsl) -> TXT
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `'PySide6' is not defined` / `ModuleNotFoundError: PySide6` | Run `pip install -r requirements.txt` (inside the venv, if you created one) |
| `miniaudio is required for MP3/FLAC/OGG` | Run `pip install miniaudio` |
| `externally-managed-environment` (Linux) | Add `--break-system-packages` as shown above |
| `Could not load the Qt platform plugin "xcb"` (Linux) | `sudo apt install libxcb-cursor0` |
| `buffer is too short` / odd PNG output | Textures are GPU-compressed (DXT/ETC/ASTC are lossy); this is expected |
| Long-path errors installing PySide6 on Windows (Microsoft Store Python) | Enable Windows long paths: run PowerShell **as Administrator** and execute `reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f`, or install the python.org build instead |
| On macOS "unidentified developer" | Right-click the app/terminal and choose *Open*, or run from a terminal as shown above |
# Building a Windows EXE

This project can be packaged into a simple Windows executable using PyInstaller.

## Prerequisites
- Windows
- Python 3.10+
- `ffmpeg` installed and available in `PATH` (verify with `ffmpeg -version`)

## Build locally (PowerShell)

Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-build.txt

pyinstaller -F -n arcaea-slicer -m arcaea_slicer
```

## Output

After building, the exe will be located at:

- `dist\arcaea-slicer.exe`

## Notes
- `ffmpeg` is **not** bundled into the exe. The exe will look for `ffmpeg` in `PATH`.
- If you want to run without installing Python, distribute only `dist\arcaea-slicer.exe` (and ensure the target machine has ffmpeg).

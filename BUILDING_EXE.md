# Building a Windows EXE

Prerequisites:
- Python 3.10+
- ffmpeg in PATH (`ffmpeg -version` works)

Build locally (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-build.txt
pyinstaller -F -n arcaea-slicer -m arcaea_slicer

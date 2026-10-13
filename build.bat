@echo off
pyinstaller --onefile --console --name AutomaticAudioSplicing --add-data "resources/base.sesx;resources" --collect-binaries soundfile --collect-submodules aas --collect-all yt_dlp --collect-all openpyxl --hidden-import=soundfile --hidden-import=rich --clean main.py

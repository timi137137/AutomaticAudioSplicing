@echo off
pyinstaller --onefile --console --name AutomaticAudioSplicing --add-data "resources/base.sesx;resources" --collect-binaries soundfile --collect-submodules aas --hidden-import=soundfile --hidden-import=rich --clean main.py

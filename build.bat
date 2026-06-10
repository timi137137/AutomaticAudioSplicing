@echo off
pyinstaller --onefile --console --name AutomaticAudioSplicing --add-data "resources/base.sesx;resources" --collect-binaries soundfile --collect-submodules facade --collect-submodules domain --collect-submodules strategies --collect-submodules builders --collect-submodules adapters --hidden-import=soundfile --hidden-import=rich --clean main.py

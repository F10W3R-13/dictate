@echo off
rem Build dist\Dictate\Dictate.exe. models and llama stay outside the exe, linked by junctions (no copies).
cd /d "%~dp0"
rem Remove junctions first so cleaning dist never touches the real models/llama folders.
if exist dist\Dictate\models rmdir dist\Dictate\models
if exist dist\Dictate\llama rmdir dist\Dictate\llama
if exist dist rmdir /s /q dist
.venv\Scripts\pyinstaller --noconfirm --windowed --name Dictate --collect-all faster_whisper --collect-all ctranslate2 --add-data "web;web" dictate.py || exit /b 1
mklink /J dist\Dictate\models models
mklink /J dist\Dictate\llama llama
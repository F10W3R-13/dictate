@echo off
rem dist\Dictate\Dictate.exe 빌드. 모델·llama.cpp는 exe에 넣지 않고 정션으로 연결(복사 없음)
cd /d "%~dp0"
.venv\Scripts\pyinstaller --noconfirm --windowed --name Dictate ^
  --collect-all faster_whisper --collect-all ctranslate2 dictate.py || exit /b 1
mklink /J dist\Dictate\models models
mklink /J dist\Dictate\llama llama

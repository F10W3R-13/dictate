# Dictate

Typeless 같은 로컬 토글 받아쓰기 (Windows, NVIDIA GPU).
`Ctrl+Shift+Space` → 녹음 시작, 다시 → Whisper large-v3-turbo로 전사 → EXAONE 4.0 1.2B로 다듬기 → 커서 위치에 붙여넣기.
RTX 4050 Laptop 기준 11.6초 음성에 전사 ~0.7s + 다듬기 ~0.4s. 전부 로컬, 무료.

트레이 아이콘: 회색 로딩 / 파랑 대기 / 빨강 녹음 / 주황 전사 중. 우클릭 → 종료.

## 준비

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

- `llama\` : [llama.cpp 릴리스](https://github.com/ggml-org/llama.cpp/releases)의 `llama-*-bin-win-cuda-12.4-x64.zip`, `cudart-llama-bin-win-cuda-12.4-x64.zip` 풀기
  (Whisper도 여기 있는 cublas64_12.dll을 같이 씀)
- `models\EXAONE-4.0-1.2B-Q8_0.gguf` : [LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF](https://huggingface.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF) — 없으면 다듬기 생략
- `models\whisper-large-v3-turbo\` : [mobiuslabsgmbh/faster-whisper-large-v3-turbo](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo) 파일들 — 없으면 첫 실행 때 자동 다운로드

## 실행

- 개발: `.venv\Scripts\python dictate.py`
- 점검: `.venv\Scripts\python dictate.py --test 녹음.wav` (16kHz 모노 16bit)
- exe: `build.bat` → `dist\Dictate\Dictate.exe` (models·llama는 정션으로 연결, 로그는 `dictate.log`)

GPU가 꺼져 있으면(배터리 절전 등) CPU로 돌아 수십 초 걸림. Lenovo는 Vantage에서 GPU 모드를 Hybrid/dGPU로.

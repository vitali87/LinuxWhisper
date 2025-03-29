# STT Copy Utility

A simple Speech-to-Text utility that records audio, transcribes it using a background Whisper server, and copies the text to the clipboard.

## Setup

1.  Install dependencies (e.g., using `uv pip install ...`).
2.  Run the FastAPI server: `python whisper_server.py`
3.  Configure a system shortcut to run `stt_copy.py` as a toggle (start/stop recording). 
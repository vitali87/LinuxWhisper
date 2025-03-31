import whisper
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import re
import time
import datetime
import sys
from dotenv import load_dotenv

# +--------------------------------------------------------------------------+
# | SECTION: Configuration & Model Loading                                   |
# +--------------------------------------------------------------------------+
load_dotenv()

MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "tiny.en")
SERVER_HOST = os.getenv("WHISPER_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("WHISPER_SERVER_PORT", "8001"))
LOG_FILE_PATH = os.getenv("WHISPER_SERVER_LOG_FILE", "/tmp/whisper_server_debug.log")
USE_FP16 = os.getenv("WHISPER_USE_FP16", "False").lower() in ("true", "1", "t")

try:
    print(f"Loading Whisper model: {MODEL_NAME}...")
    model = whisper.load_model(MODEL_NAME)
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"FATAL: Failed to load Whisper model '{MODEL_NAME}': {e}")
    exit(1)

# +--------------------------------------------------------------------------+
# | SECTION: FastAPI Setup                                                    |
# +--------------------------------------------------------------------------+
app = FastAPI()


class TranscriptionRequest(BaseModel):
    audio_path: str


# +--------------------------------------------------------------------------+
# | SECTION: API Endpoints                                                   |
# +--------------------------------------------------------------------------+
@app.post("/transcribe")
async def transcribe_audio(request: TranscriptionRequest):
    """Accepts the path to an audio file and returns the transcription."""
    audio_path = request.audio_path
    log_message(f"Received request to transcribe: {audio_path}")

    if not os.path.exists(audio_path):
        error_msg = f"Error: Audio file not found at path: {audio_path}"
        log_message(error_msg)
        raise HTTPException(
            status_code=400, detail=f"Audio file not found: {audio_path}"
        )

    transcribe_start_time = time.time()
    try:
        log_message(f"Starting transcription for: {audio_path} (FP16: {USE_FP16})")
        result = model.transcribe(audio_path, language="en", fp16=USE_FP16)
        transcription_text = result.get("text", "")

        cleaned_text = re.sub(
            r"^\\[\\d{2}:\\d{2}\\.\\d{3} --> \\d{2}:\\d{2}\\.\\d{3}\\]\\s*",
            "",
            transcription_text,
        )
        final_text = cleaned_text.strip()

        transcribe_duration = time.time() - transcribe_start_time
        log_message(
            f"Transcription successful in {transcribe_duration:.4f}s: {final_text[:100]}..."
        )

        log_message(f"Sending response for: {audio_path}")
        return {"transcription": final_text}

    except Exception as e:
        transcribe_duration = time.time() - transcribe_start_time
        log_message(
            f"Error during transcription for {audio_path} after {transcribe_duration:.4f}s: {e}"
        )
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}") from e


# +--------------------------------------------------------------------------+
# | SECTION: Utilities                                                       |
# +--------------------------------------------------------------------------+
def log_message(message):
    """Appends a timestamped message to the log file."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"{now} - {message}\n")
    except IOError as e:
        print(f"SERVER LOGGING FAILED: {e}", file=sys.stderr)
        print(f"{now} - {message}", file=sys.stderr)


# +--------------------------------------------------------------------------+
# | SECTION: Main Execution                                                  |
# +--------------------------------------------------------------------------+
if __name__ == "__main__":
    log_message(
        f"Starting Whisper API server on {SERVER_HOST}:{SERVER_PORT} with model {MODEL_NAME}"
    )
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")

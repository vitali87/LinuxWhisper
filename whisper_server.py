import whisper
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import re  # Keep regex for potential timestamp cleaning
import time  # Import time for timing
import datetime  # Import datetime for timestamp
import sys  # Import sys for stderr
from dotenv import load_dotenv  # Import dotenv

load_dotenv()  # Load variables from .env file into environment

# --- Configuration ---
# Read settings from environment variables with defaults
MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "tiny.en")
SERVER_HOST = os.getenv("WHISPER_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("WHISPER_SERVER_PORT", "8001"))
LOG_FILE_PATH = os.getenv("WHISPER_SERVER_LOG_FILE", "/tmp/whisper_server_debug.log")
# Consider adding USE_FP16 config via env var too
USE_FP16 = os.getenv("WHISPER_USE_FP16", "False").lower() in ("true", "1", "t")

# --- Load Model ---
# Load the model globally when the server starts
try:
    print(f"Loading Whisper model: {MODEL_NAME}...")
    model = whisper.load_model(MODEL_NAME)
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"FATAL: Failed to load Whisper model '{MODEL_NAME}': {e}")
    # Exit if model loading fails, as the server is useless without it
    exit(1)

# --- FastAPI App ---
app = FastAPI()


class TranscriptionRequest(BaseModel):
    audio_path: str


# --- API Endpoint ---
@app.post("/transcribe")
async def transcribe_audio(request: TranscriptionRequest):
    """
    Accepts the path to an audio file and returns the transcription.
    """
    audio_path = request.audio_path
    log_message(
        f"Received request to transcribe: {audio_path}"
    )  # Use log_message on server too

    if not os.path.exists(audio_path):
        error_msg = f"Error: Audio file not found at path: {audio_path}"
        log_message(error_msg)
        raise HTTPException(
            status_code=400, detail=f"Audio file not found: {audio_path}"
        )

    transcribe_start_time = time.time()
    try:
        log_message(f"Starting transcription for: {audio_path} (FP16: {USE_FP16})")
        # Perform the transcription using the pre-loaded model
        # Note: whisper.transcribe() when used as library might have different default verbosity
        result = model.transcribe(
            audio_path, language="en", fp16=USE_FP16
        )  # Use configured FP16 setting
        transcription_text = result.get("text", "")

        # Optional: Clean timestamps if they appear even in library mode
        # (Unlikely for model.transcribe result['text'], but keep just in case)
        cleaned_text = re.sub(
            r"^\\[\\d{2}:\\d{2}\\.\\d{3} --> \\d{2}:\\d{2}\\.\\d{3}\\]\\s*",
            "",
            transcription_text,
        )
        final_text = cleaned_text.strip()

        transcribe_duration = time.time() - transcribe_start_time  # Calculate duration
        log_message(
            f"Transcription successful in {transcribe_duration:.4f}s: {final_text[:100]}..."
        )  # Log duration and beginning of result

        log_message(f"Sending response for: {audio_path}")
        return {"transcription": final_text}

    except Exception as e:
        transcribe_duration = time.time() - transcribe_start_time
        log_message(
            f"Error during transcription for {audio_path} after {transcribe_duration:.4f}s: {e}"
        )
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")


# --- Logging Setup for Server ---
# (Assuming same log file for simplicity, or choose a different one)
# LOG_FILE_PATH is now defined in Configuration section


def log_message(message):
    """Appends a timestamped message to the log file."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"{now} - {message}\n")
    except IOError as e:
        print(f"SERVER LOGGING FAILED: {e}", file=sys.stderr)
        print(f"{now} - {message}", file=sys.stderr)


# --- Run Server ---
if __name__ == "__main__":
    log_message(
        f"Starting Whisper API server on {SERVER_HOST}:{SERVER_PORT} with model {MODEL_NAME}"
    )  # Log server start details
    # Redirect uvicorn logs potentially?
    # For now, use default uvicorn logging + our file logging
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")

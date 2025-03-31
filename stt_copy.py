#!/usr/bin/env python3
import subprocess
import tempfile
import os
import sys
import shlex
import requests
import time
import signal
import json
from dotenv import load_dotenv
from loguru import logger

# +--------------------------------------------------------------------------+
# | SECTION: Configuration                                                   |
# +--------------------------------------------------------------------------+
load_dotenv()

SAMPLE_RATE = int(os.getenv("STT_SAMPLE_RATE", "16000"))
SERVER_URL = os.getenv("STT_SERVER_URL", "http://127.0.0.1:8001/transcribe")
STATE_FILE_PATH = os.getenv("STT_STATE_FILE", "/tmp/stt_recording_state.json")
LOG_FILE_PATH = os.getenv("STT_COPY_LOG_FILE", "/tmp/stt_copy_debug.log")
LOCK_FILE_PATH = os.getenv("STT_LOCK_FILE", "/tmp/stt_copy_lock")
POST_KILL_SLEEP = float(os.getenv("STT_POST_KILL_SLEEP", "0.1"))

# +--------------------------------------------------------------------------+
# | SECTION: Logger Setup                                                    |
# +--------------------------------------------------------------------------+
logger.add(sys.stderr, level="INFO")
if LOG_FILE_PATH:
    try:
        logger.add(
            LOG_FILE_PATH,
            level="DEBUG",
            rotation="10 MB",
            enqueue=True,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
        )
        logger.info(f"File logging configured to: {LOG_FILE_PATH}")
    except Exception as e:
        logger.error(f"Failed to configure file logging to {LOG_FILE_PATH}: {e}")
        LOG_FILE_PATH = None
else:
    logger.warning("Log file path not set. File logging disabled.")


# +--------------------------------------------------------------------------+
# | SECTION: Utilities                                                       |
# +--------------------------------------------------------------------------+
def run_command(command):
    try:
        command_list = shlex.split(command) if isinstance(command, str) else command
        result = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        logger.exception("Fatal Error running command")
        return "", f"Failed to run command: {e}", 1


# +--------------------------------------------------------------------------+
# | SECTION: Recording Stop Helpers                                          |
# +--------------------------------------------------------------------------+
def _kill_arecord_process(pid: int) -> float:
    """Attempts to terminate the arecord process and returns the duration."""
    kill_start_time = time.time()
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Sent SIGTERM to arecord process (PID: {pid}).")
    except ProcessLookupError:
        logger.info(f"Process {pid} not found. Already stopped?")
    except Exception as e:
        logger.error(f"Error stopping arecord (PID: {pid}): {e}")
        raise  # Re-raise after logging to handle upstream
    return time.time() - kill_start_time


def _remove_state_file(file_path: str) -> None:
    """Removes the state file if it exists."""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"Removed state file: {file_path}")
        except OSError as e:
            logger.warning(f"Could not remove state file {file_path}: {e}")


def _validate_wav_file(wav_filename: str) -> float:
    """Checks if the WAV file exists and is not empty. Returns duration."""
    file_check_start_time = time.time()
    if not os.path.exists(wav_filename):
        error_msg = f"Error: Recorded audio file is missing: {wav_filename}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    if os.path.getsize(wav_filename) < 1024:  # Basic check for non-empty file
        error_msg = (
            f"Error: Recorded audio file seems empty or too small: {wav_filename}"
        )
        logger.error(error_msg)
        try:
            os.remove(wav_filename)
            logger.info(f"Removed empty/small wav file: {wav_filename}")
        except OSError as e:
            logger.error(f"Error removing empty wav file: {e}")
            raise ValueError(error_msg) from e
        raise ValueError(error_msg)

    return time.time() - file_check_start_time


def _transcribe_audio(wav_filename: str) -> tuple[str, float]:
    """Sends audio file to transcription server and returns text and duration."""
    logger.info(f"Sending {wav_filename} to transcription server at {SERVER_URL}...")
    request_start_time = time.time()
    final_text = ""
    try:
        response = requests.post(
            SERVER_URL, json={"audio_path": wav_filename}, timeout=30
        )
        response.raise_for_status()
        result_json = response.json()
        final_text = result_json.get("transcription", "")

        if not final_text:
            logger.warning("Transcription result from server is empty.")
            raise ValueError("Empty transcription received from server.")

        logger.info(f"Transcription received: {final_text[:50]}...")
        return final_text, time.time() - request_start_time

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Error: Could not connect to transcription server at {SERVER_URL}."
        logger.error(f"{error_msg}\nIs whisper_server.py running?")
        raise ConnectionError(error_msg) from e
    except requests.exceptions.RequestException as e:
        error_msg = f"Error during transcription request: {e}"
        logger.exception(f"Error during transcription request: {e}")
        raise  # Re-raise the specific requests error
    except Exception as e:
        error_msg = f"Unexpected error processing transcription response: {e}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e


def _copy_to_clipboard(text: str) -> float:
    """Copies text to the system clipboard using xclip. Returns duration."""
    logger.info(f"Copying text to clipboard: {text[:50]}...")
    copy_start_time = time.time()
    copy_cmd = ["xclip", "-selection", "clipboard"]
    try:
        process = subprocess.run(
            copy_cmd,
            input=text,
            text=True,
            check=True,
            timeout=5,
            capture_output=True,
        )
        logger.info("Successfully copied text to clipboard.")
    except FileNotFoundError:
        logger.warning("'xclip' command not found. Cannot copy to clipboard.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy (xclip error): {e}. stderr: {e.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Timeout expired while trying to copy with xclip.")
    except Exception as e:
        logger.exception("An unexpected error occurred during clipboard copy")
    return time.time() - copy_start_time


def _cleanup_wav_file(wav_filename: str) -> float:
    """Deletes the temporary WAV file. Returns duration."""
    delete_start_time = time.time()
    if os.path.exists(wav_filename):
        try:
            os.remove(wav_filename)
            logger.info(f"Deleted temporary file: {wav_filename}")
        except OSError as e:
            logger.error(f"Error deleting temp file {wav_filename}: {e}")
    return time.time() - delete_start_time


def _log_stop_timings(timings: dict):
    """Logs the durations of various steps in the stop process."""
    logger.debug("--- STOP RECORDING TIMINGS ---")
    logger.debug(f"Kill Signal:      {timings.get('kill', 0):.4f}s")
    logger.debug(f"Post-Kill Sleep:  {timings.get('sleep', 0):.4f}s")
    logger.debug(f"File Check:       {timings.get('file_check', 0):.4f}s")
    logger.debug(f"Server Req:       {timings.get('request', 0):.4f}s")
    logger.debug(f"XCLIP Copy:       {timings.get('copy', 0):.4f}s")
    logger.debug(f"WAV Delete:       {timings.get('wav_delete', 0):.4f}s")
    logger.debug(f"Total Stop Func:  {timings.get('total', 0):.4f}s")
    logger.debug("----------------------------- ")


# +--------------------------------------------------------------------------+
# | SECTION: Main Recording Control Functions                                |
# +--------------------------------------------------------------------------+
def stop_recording(state):
    """Stops recording, transcribes, copies text, and cleans up."""
    overall_start_time = time.time()
    timings = {}

    pid = state.get("pid")
    wav_filename = state.get("wav_file")

    if not pid or not wav_filename:
        logger.error("Invalid state loaded. Cannot stop recording.")
        _remove_state_file(STATE_FILE_PATH)
        sys.exit(1)

    logger.info(f"Attempting to stop recording (PID: {pid}, File: {wav_filename})...")

    try:
        timings["kill"] = _kill_arecord_process(pid)

        sleep_start_time = time.time()
        time.sleep(POST_KILL_SLEEP)
        timings["sleep"] = time.time() - sleep_start_time

        _remove_state_file(STATE_FILE_PATH)

        timings["file_check"] = _validate_wav_file(wav_filename)

        final_text, timings["request"] = _transcribe_audio(wav_filename)

        timings["copy"] = _copy_to_clipboard(final_text)

    except (
        FileNotFoundError,
        ValueError,
        ConnectionError,
        RuntimeError,
        requests.exceptions.RequestException,
    ) as e:
        logger.error(f"Stopping process failed: {e}")
        _cleanup_wav_file(wav_filename)
        _remove_state_file(STATE_FILE_PATH)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during stop_recording")
        _cleanup_wav_file(wav_filename)
        _remove_state_file(STATE_FILE_PATH)
        sys.exit(1)
    finally:
        timings["wav_delete"] = _cleanup_wav_file(wav_filename)

        timings["total"] = time.time() - overall_start_time
        _log_stop_timings(timings)


def start_recording():
    logger.info("Starting recording...")

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            wav_filename = tmp_wav.name
        logger.info(f"Recording to temporary file: {wav_filename}")
    except Exception as e:
        logger.error(f"Error creating temp file: {e}")
        sys.exit(1)

    record_cmd = [
        "arecord",
        "-q",
        "-D",
        "default",
        "-f",
        "S16_LE",
        "-r",
        str(SAMPLE_RATE),
        "-t",
        "wav",
        wav_filename,
    ]

    try:
        process = subprocess.Popen(
            record_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        pid = process.pid
        logger.info(f"arecord started in background (PID: {pid})")
    except FileNotFoundError:
        logger.error("Error: arecord command not found.")
        if "wav_filename" in locals() and os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)
    except Exception as e:
        logger.exception("Error starting arecord")
        if "wav_filename" in locals() and os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)

    state = {"pid": pid, "wav_file": wav_filename}
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f)
        logger.info(f"State file created: {STATE_FILE_PATH}")
    except IOError as e:
        logger.error(f"Error writing state file {STATE_FILE_PATH}: {e}")
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as kill_e:
            logger.error(f"Also failed to kill stray arecord process {pid}: {kill_e}")
        if os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)


# +--------------------------------------------------------------------------+
# | SECTION: Main Execution                                                  |
# +--------------------------------------------------------------------------+
def main():
    logger.debug("Inside main(). Checking for state file...")
    state_file_exists = os.path.exists(STATE_FILE_PATH)
    logger.info(f"State file '{STATE_FILE_PATH}' exists: {state_file_exists}")

    if state_file_exists:
        logger.info("State file found. Attempting to stop recording.")
        try:
            with open(STATE_FILE_PATH, "r") as f:
                state = json.load(f)
            stop_recording(state)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(
                f"Error reading state file {STATE_FILE_PATH}: {e}. Attempting cleanup."
            )
            try:
                os.remove(STATE_FILE_PATH)
            except OSError as remove_e:
                logger.error(f"Failed to remove corrupt state file: {remove_e}")
                sys.exit(1)
    else:
        logger.info("State file NOT found. Attempting to start recording.")
        start_recording()


if __name__ == "__main__":
    logger.info("Script execution started.")

    lock_file_path = LOCK_FILE_PATH
    lock_acquired = False
    try:
        logger.debug("Attempting to acquire lock...")
        lock_dir = os.path.dirname(lock_file_path)
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)

        fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        logger.debug(f"os.open succeeded (fd: {fd})")
        os.close(fd)
        logger.debug("os.close succeeded")
        lock_acquired = True
        logger.info("Lock acquired successfully.")
    except FileExistsError:
        logger.warning("Script is already running (lock file exists). Exiting.")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Failed to create or acquire lock file {lock_file_path}")
        sys.exit(1)

    logger.debug(f"Checking if lock was acquired: {lock_acquired}")
    if lock_acquired:
        logger.info("Proceeding to main function call...")
        try:
            main()
            logger.info("main() function completed successfully.")
        except Exception as main_e:
            logger.exception("Critical error during main() execution")
        finally:
            logger.debug("Entering finally block for lock removal.")
            if os.path.exists(lock_file_path):
                try:
                    os.remove(lock_file_path)
                    logger.info(f"Deleted lock file: {lock_file_path}")
                except OSError as e:
                    logger.error(f"Error removing lock file {lock_file_path}: {e}")
            else:
                logger.warning("Lock file did not exist in finally block.")
    else:
        logger.warning("Exiting because lock was not acquired.")

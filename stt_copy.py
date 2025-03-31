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
from datetime import datetime
from dotenv import load_dotenv

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
# | SECTION: Utilities                                                       |
# +--------------------------------------------------------------------------+
def log_message(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"{now} - {message}\n")
    except IOError as e:
        print(f"LOGGING FAILED: {e}", file=sys.stderr)
        print(f"{now} - {message}", file=sys.stderr)


def notify(message, duration=2000):
    # Placeholder for notification logic, e.g., using notify-send
    # command = ["notify-send", "-t", str(duration), "STT", message]
    # run_command(command)
    pass


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
        log_message(f"Fatal Error running command: {e}")
        return "", f"Failed to run command: {e}", 1


# +--------------------------------------------------------------------------+
# | SECTION: Recording Stop Helpers                                          |
# +--------------------------------------------------------------------------+
def _kill_arecord_process(pid: int) -> float:
    """Attempts to terminate the arecord process and returns the duration."""
    kill_start_time = time.time()
    try:
        os.kill(pid, signal.SIGTERM)
        log_message(f"Sent SIGTERM to arecord process (PID: {pid}).")
    except ProcessLookupError:
        log_message(f"Info: Process {pid} not found. Already stopped?")
    except Exception as e:
        log_message(f"Error stopping arecord (PID: {pid}): {e}")
        raise  # Re-raise after logging to handle upstream
    return time.time() - kill_start_time


def _remove_state_file(file_path: str) -> None:
    """Removes the state file if it exists."""
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            log_message(f"Removed state file: {file_path}")
        except OSError as e:
            # Log as warning, as the main process might continue
            log_message(f"Warning: Could not remove state file {file_path}: {e}")


def _validate_wav_file(wav_filename: str) -> float:
    """Checks if the WAV file exists and is not empty. Returns duration."""
    file_check_start_time = time.time()
    if not os.path.exists(wav_filename):
        error_msg = f"Error: Recorded audio file is missing: {wav_filename}"
        log_message(error_msg)
        raise FileNotFoundError(error_msg)

    if os.path.getsize(wav_filename) < 1024:  # Basic check for non-empty file
        error_msg = (
            f"Error: Recorded audio file seems empty or too small: {wav_filename}"
        )
        log_message(error_msg)
        # Attempt to remove the problematic file before raising
        try:
            os.remove(wav_filename)
            log_message(f"Removed empty/small wav file: {wav_filename}")
        except OSError as e:
            log_message(f"Error removing empty wav file: {e}")
        raise ValueError(error_msg)

    return time.time() - file_check_start_time


def _transcribe_audio(wav_filename: str) -> tuple[str, float]:
    """Sends audio file to transcription server and returns text and duration."""
    log_message(f"Sending {wav_filename} to transcription server at {SERVER_URL}...")
    request_start_time = time.time()
    final_text = ""
    try:
        response = requests.post(
            SERVER_URL, json={"audio_path": wav_filename}, timeout=30
        )
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        result_json = response.json()
        final_text = result_json.get("transcription", "")

        if not final_text:
            log_message("Transcription result from server is empty.")
            raise ValueError("Empty transcription received from server.")

        log_message(f"Transcription received: {final_text[:50]}...")
        return final_text, time.time() - request_start_time

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Error: Could not connect to transcription server at {SERVER_URL}."
        log_message(f"{error_msg}\nIs whisper_server.py running?")
        raise ConnectionError(error_msg) from e
    except (
        requests.exceptions.RequestException
    ) as e:  # Catches other request errors (timeout, HTTPError, etc.)
        error_msg = f"Error during transcription request: {e}"
        log_message(error_msg)
        raise  # Re-raise the specific requests error
    except Exception as e:  # Catch unexpected errors during response processing
        error_msg = f"Unexpected error processing transcription response: {e}"
        log_message(error_msg)
        raise RuntimeError(error_msg) from e


def _copy_to_clipboard(text: str) -> float:
    """Copies text to the system clipboard using xclip. Returns duration."""
    log_message(f"Copying text to clipboard: {text[:50]}...")
    copy_start_time = time.time()
    copy_cmd = ["xclip", "-selection", "clipboard"]
    try:
        # Using input=text directly is preferred and safer
        process = subprocess.run(
            copy_cmd,
            input=text,
            text=True,
            check=True,  # Raise CalledProcessError on non-zero exit
            timeout=5,
            capture_output=True,  # Capture stdout/stderr for better debugging
        )
        log_message("Successfully copied text to clipboard.")
    except FileNotFoundError:
        log_message("Error: 'xclip' command not found. Cannot copy to clipboard.")
        # Don't raise, just log, as it might not be critical for everyone
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to copy (xclip error): {e}. stderr: {e.stderr}")
    except subprocess.TimeoutExpired:
        log_message("Error: Timeout expired while trying to copy with xclip.")
    except Exception as e:
        # Catch any other unexpected errors
        log_message(f"An unexpected error occurred during clipboard copy: {e}")
    return time.time() - copy_start_time


def _cleanup_wav_file(wav_filename: str) -> float:
    """Deletes the temporary WAV file. Returns duration."""
    delete_start_time = time.time()
    if os.path.exists(wav_filename):
        try:
            os.remove(wav_filename)
            log_message(f"Deleted temporary file: {wav_filename}")
        except OSError as e:
            log_message(f"Error deleting temp file {wav_filename}: {e}")
            # Log error but don't raise, cleanup failure is not ideal but shouldn't halt everything
    return time.time() - delete_start_time


def _log_stop_timings(timings: dict):
    """Logs the durations of various steps in the stop process."""
    log_message("--- STOP RECORDING TIMINGS ---")
    log_message(f"Kill Signal:      {timings.get('kill', 0):.4f}s")
    log_message(f"Post-Kill Sleep:  {timings.get('sleep', 0):.4f}s")
    log_message(f"File Check:       {timings.get('file_check', 0):.4f}s")
    log_message(f"Server Req:       {timings.get('request', 0):.4f}s")
    log_message(f"XCLIP Copy:       {timings.get('copy', 0):.4f}s")
    # log_message(f"Notify Copy:      {timings.get('notify_copy', 0):.4f}s") # Removed notify timing
    log_message(f"WAV Delete:       {timings.get('wav_delete', 0):.4f}s")
    log_message(f"Total Stop Func:  {timings.get('total', 0):.4f}s")
    log_message("----------------------------- ")


# +--------------------------------------------------------------------------+
# | SECTION: Main Recording Control Functions                                |
# +--------------------------------------------------------------------------+
def stop_recording(state):
    """Stops recording, transcribes, copies text, and cleans up."""
    overall_start_time = time.time()
    timings = {}

    pid = state.get("pid")
    wav_filename = state.get("wav_file")

    # 1. Validate State
    if not pid or not wav_filename:
        log_message("Error: Invalid state loaded. Cannot stop recording.")
        _remove_state_file(STATE_FILE_PATH)  # Attempt cleanup
        sys.exit(1)

    log_message(f"Attempting to stop recording (PID: {pid}, File: {wav_filename})...")

    try:
        # 2. Kill Process
        timings["kill"] = _kill_arecord_process(pid)

        # 3. Post-Kill Sleep (Allow filesystem time to sync, etc.)
        sleep_start_time = time.time()
        time.sleep(POST_KILL_SLEEP)
        timings["sleep"] = time.time() - sleep_start_time

        # 4. Remove State File (Done early after kill signal)
        _remove_state_file(STATE_FILE_PATH)

        # 5. Validate Audio File
        timings["file_check"] = _validate_wav_file(wav_filename)

        # 6. Transcribe Audio
        final_text, timings["request"] = _transcribe_audio(wav_filename)

        # 7. Copy to Clipboard
        timings["copy"] = _copy_to_clipboard(final_text)

        # 8. Notify User (Optional)
        # notify_start_time = time.time()
        notify(f"Copied: {final_text[:30]}...")
        # timings["notify_copy"] = time.time() - notify_start_time

    except (
        FileNotFoundError,
        ValueError,
        ConnectionError,
        RuntimeError,
        requests.exceptions.RequestException,
    ) as e:
        # Handle errors from helper functions gracefully
        log_message(f"Stopping process failed: {e}")
        # Ensure cleanup even on error
        _cleanup_wav_file(wav_filename)  # Attempt to delete wav file
        _remove_state_file(STATE_FILE_PATH)  # Ensure state file is gone
        sys.exit(1)
    except Exception as e:
        # Catch any unexpected errors during the main flow
        log_message(f"Unexpected error during stop_recording: {e}")
        _cleanup_wav_file(wav_filename)
        _remove_state_file(STATE_FILE_PATH)
        sys.exit(1)
    finally:
        # 9. Cleanup WAV file (always runs)
        timings["wav_delete"] = _cleanup_wav_file(wav_filename)

        # 10. Log Timings
        timings["total"] = time.time() - overall_start_time
        _log_stop_timings(timings)


def start_recording():
    log_message("Starting recording...")

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            wav_filename = tmp_wav.name
        log_message(f"Recording to temporary file: {wav_filename}")
    except Exception as e:
        log_message(f"Error creating temp file: {e}")
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
        log_message(f"arecord started in background (PID: {pid})")
    except FileNotFoundError:
        log_message("Error: arecord command not found.")
        if "wav_filename" in locals() and os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)
    except Exception as e:
        log_message(f"Error starting arecord: {e}")
        if "wav_filename" in locals() and os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)

    state = {"pid": pid, "wav_file": wav_filename}
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f)
        log_message(f"State file created: {STATE_FILE_PATH}")
    except IOError as e:
        log_message(f"Error writing state file {STATE_FILE_PATH}: {e}")
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as kill_e:
            log_message(f"Also failed to kill stray arecord process {pid}: {kill_e}")
        if os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)


# +--------------------------------------------------------------------------+
# | SECTION: Main Execution                                                  |
# +--------------------------------------------------------------------------+
def main():
    log_message("Inside main(). Checking for state file...")
    state_file_exists = os.path.exists(STATE_FILE_PATH)
    log_message(f"State file '{STATE_FILE_PATH}' exists: {state_file_exists}")

    if state_file_exists:
        log_message("State file found. Attempting to stop recording.")
        try:
            with open(STATE_FILE_PATH, "r") as f:
                state = json.load(f)
            stop_recording(state)
        except (IOError, json.JSONDecodeError) as e:
            log_message(
                f"Error reading state file {STATE_FILE_PATH}: {e}. Attempting cleanup."
            )
            try:
                os.remove(STATE_FILE_PATH)
            except OSError as remove_e:
                log_message(f"Failed to remove corrupt state file: {remove_e}")
                sys.exit(1)
    else:
        log_message("State file NOT found. Attempting to start recording.")
        start_recording()


if __name__ == "__main__":
    script_start_success = False
    try:
        log_message("Script execution started.")
        script_start_success = True
    except Exception as log_init_e:
        log_message(f"Initial log message failed: {log_init_e}")

    lock_file_path = LOCK_FILE_PATH
    lock_acquired = False
    if script_start_success:
        try:
            log_message("Attempting to acquire lock...")
            fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            log_message(f"os.open succeeded (fd: {fd})")
            os.close(fd)
            log_message("os.close succeeded")
            lock_acquired = True
            log_message("Lock acquired successfully.")
        except FileExistsError:
            log_message("Script is already running (lock file exists). Exiting.")
            sys.exit(1)
        except Exception as e:
            log_message(f"ERROR: Failed to create lock file {lock_file_path}: {e}")
            sys.exit(1)
    else:
        print("Script start logging failed, cannot proceed safely.", file=sys.stderr)
        sys.exit(1)

    log_message(f"Checking if lock was acquired: {lock_acquired}")
    if lock_acquired:
        log_message("Proceeding to main function call...")
        try:
            main()
            log_message("main() function completed.")
        except Exception as main_e:
            log_message(f"ERROR during main() execution: {main_e}")
        finally:
            if os.path.exists(lock_file_path):
                try:
                    os.remove(lock_file_path)
                    log_message(f"Deleted lock file: {lock_file_path}")
                except OSError as e:
                    log_message(f"Error removing lock file {lock_file_path}: {e}")
            else:
                log_message("Lock file did not exist in finally block.")
    else:
        log_message("Exiting because lock was not acquired.")

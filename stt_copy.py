#!/home/vitali/Documents/stt/.venv/bin/python
import subprocess
import tempfile
import os
import sys
import shlex
import requests
import time
import signal
import json
from datetime import datetime  # Import datetime for timestamps

# Configuration
SAMPLE_RATE = 16000
SERVER_URL = "http://127.0.0.1:8001/transcribe"
STATE_FILE_PATH = "/tmp/stt_recording_state.json"  # File to store recording state
LOG_FILE_PATH = "/tmp/stt_copy_debug.log"  # Dedicated log file


# --- Logging Function ---
def log_message(message):
    """Appends a timestamped message to the log file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Timestamp with ms
    try:
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"{now} - {message}\n")
    except IOError as e:
        # Fallback to stderr if logging fails
        print(f"LOGGING FAILED: {e}", file=sys.stderr)
        print(f"{now} - {message}", file=sys.stderr)


# Keep notify function
def notify(message, duration=2000):
    """Sends a desktop notification."""
    # try:
    #     subprocess.run(
    #         ["notify-send", "-t", str(duration), f"STT: {message}"],
    #         check=True,
    #         timeout=5,
    #         capture_output=True,  # Prevent notify-send outputting to terminal
    #     )
    # except Exception as e:
    #     # print(f"Notification Error: {e}", file=sys.stderr)
    #     log_message(f"Notification Error: {e}")
    pass  # Keep function definition but make it do nothing


# Keep run_command (might be useful for xclip still, or future additions)
def run_command(command):
    """Runs a command, captures output, returns (stdout, stderr, returncode)."""
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
        # notify(f"Error running command: {e}", duration=5000)
        # print(f"Fatal Error running command: {e}", file=sys.stderr)
        log_message(f"Fatal Error running command: {e}")
        return "", f"Failed to run command: {e}", 1


def stop_recording(state):
    """Stops the recording process and handles transcription."""
    start_stop_time = time.time()  # START TIMING

    pid = state.get("pid")
    wav_filename = state.get("wav_file")

    if not pid or not wav_filename:
        # notify("Error: Invalid state file.", 4000)
        # print("Error: Invalid state found.", file=sys.stderr)
        log_message("Error: Invalid state found.")
        # Clean up state file if possible
        if os.path.exists(STATE_FILE_PATH):
            try:
                os.remove(STATE_FILE_PATH)
            except OSError as e:
                # print(f"Error removing state file: {e}", file=sys.stderr)
                log_message(f"Error removing state file: {e}")
        sys.exit(1)

    # print(f"Stopping recording (PID: {pid})...")
    log_message(f"Stopping recording (PID: {pid})...")
    # notify("Stopping recording...", 1000)

    kill_duration = 0
    sleep_duration = 0
    try:
        kill_start_time = time.time()
        # Send SIGTERM to arecord process
        os.kill(pid, signal.SIGTERM)
        kill_duration = time.time() - kill_start_time
    except ProcessLookupError:
        # print(f"Info: Process {pid} not found. Already stopped?", file=sys.stderr)
        log_message(f"Info: Process {pid} not found. Already stopped?")
        # Continue assuming file might be complete
    except Exception as e:
        # notify(f"Error stopping arecord: {e}", 4000)
        # print(f"Error stopping arecord (PID: {pid}): {e}", file=sys.stderr)
        log_message(f"Error stopping arecord (PID: {pid}): {e}")
        # Attempt cleanup and exit
        if os.path.exists(STATE_FILE_PATH):
            os.remove(STATE_FILE_PATH)
        if os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)

    # Wait a short time for the process to terminate and file to write
    sleep_start_time = time.time()
    time.sleep(0.1)  # Try reducing sleep from 0.5s to 0.1s
    sleep_duration = time.time() - sleep_start_time

    # Delete state file FIRST to prevent double-stops if something goes wrong
    if os.path.exists(STATE_FILE_PATH):
        try:
            os.remove(STATE_FILE_PATH)
        except OSError as e:
            # print(f"Warning: Could not remove state file {STATE_FILE_PATH}: {e}",
            #       file=sys.stderr,)
            log_message(f"Warning: Could not remove state file {STATE_FILE_PATH}: {e}")

    file_check_duration = 0
    # Check if the WAV file exists and has reasonable size
    file_check_start_time = time.time()
    if not os.path.exists(wav_filename) or os.path.getsize(wav_filename) < 1024:
        error_msg = "Error: Recorded audio file is missing or empty."
        # notify(error_msg, 4000)
        # print(f"{error_msg} Path: {wav_filename}", file=sys.stderr)
        log_message(f"{error_msg} Path: {wav_filename}")
        # Attempt to clean up wav file if it exists but is small
        if os.path.exists(wav_filename):
            try:
                os.remove(wav_filename)
            except OSError as e:
                # print(f"Error removing empty wav file: {e}", file=sys.stderr)
                log_message(f"Error removing empty wav file: {e}")
        sys.exit(1)
    file_check_duration = time.time() - file_check_start_time

    # print(f"Sending {wav_filename} to transcription server...")
    log_message(f"Sending {wav_filename} to transcription server...")
    # notify("Transcribing...", 1000)

    # --- Call Transcription Server ---
    request_duration = 0
    final_text = ""  # Ensure final_text is defined
    request_start_time = time.time()
    try:
        response = requests.post(
            SERVER_URL, json={"audio_path": wav_filename}, timeout=30
        )
        response.raise_for_status()
        result_json = response.json()
        final_text = result_json.get("transcription", "")

        if not final_text:
            # notify("Transcription result from server is empty.", 3000)
            # print("Transcription result from server empty.", file=sys.stderr)
            log_message("Transcription result from server empty.")
            # Clean up wav file before exiting
            if os.path.exists(wav_filename):
                os.remove(wav_filename)
            sys.exit(1)

    except requests.exceptions.ConnectionError:
        error_msg = "Error: Could not connect to transcription server."
        # notify(error_msg, 5000)
        # print(f"{error_msg}\nIs whisper_server.py running?", file=sys.stderr)
        log_message(f"{error_msg}\nIs whisper_server.py running?")
        if os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)
    # Add other requests exception handling as before...
    except Exception as e:
        error_msg = f"Error during transcription request: {e}"
        # notify(error_msg, 5000)
        # print(error_msg, file=sys.stderr)
        log_message(
            f"Error during transcription request: {error_msg}"
        )  # Log the specific error
        if os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)
    request_duration = time.time() - request_start_time

    # --- Copy to Clipboard ---
    # print(f"Copying text to clipboard: {final_text[:50]}...")
    log_message(f"Copying text to clipboard: {final_text[:50]}...")
    copy_cmd = ["xclip", "-selection", "clipboard"]
    copy_duration = 0
    copy_start_time = time.time()
    try:
        copy_proc = subprocess.run(
            copy_cmd, input=final_text, text=True, check=True, timeout=5
        )
        # notify("Text copied to clipboard.", 2000)
    except Exception as e:
        # notify(f"Failed to copy to clipboard: {e}", 4000)
        # print(f"Failed to copy (xclip error): {e}", file=sys.stderr)
        log_message(f"Failed to copy (xclip error): {e}")
        # Don't exit, just report copy error
    copy_duration = time.time() - copy_start_time

    notify_copy_duration = 0
    notify_copy_start_time = time.time()
    # try:
    #     notify("Text copied to clipboard.", 2000)
    # except Exception as e:
    #     # print(f"Notification Error during copy confirm: {e}", file=sys.stderr)
    #     log_message(f"Notification Error during copy confirm: {e}")
    notify_copy_duration = time.time() - notify_copy_start_time

    # --- Clean up WAV file ---
    wav_delete_duration = 0  # Initialize outside finally
    try:
        # Code that might raise exception before finally
        pass
    finally:  # Use finally block for WAV cleanup
        wav_delete_start_time = time.time()
        if os.path.exists(wav_filename):
            try:
                os.remove(wav_filename)
                # print(f"Deleted temporary file: {wav_filename}")
                log_message(f"Deleted temporary file: {wav_filename}")
            except OSError as e:
                # print(f"Error deleting temp file {wav_filename}: {e}", file=sys.stderr)
                log_message(f"Error deleting temp file {wav_filename}: {e}")
        wav_delete_duration = time.time() - wav_delete_start_time

    # Print durations at the end of stop_recording
    total_stop_duration = time.time() - start_stop_time
    # print(f"--- STOP RECORDING TIMINGS ---", file=sys.stderr)
    log_message(f"--- STOP RECORDING TIMINGS ---")
    # print(f"Kill Signal:      {kill_duration:.4f}s", file=sys.stderr)
    log_message(f"Kill Signal:      {kill_duration:.4f}s")
    # print(f"Post-Kill Sleep:  {sleep_duration:.4f}s", file=sys.stderr)
    log_message(f"Post-Kill Sleep:  {sleep_duration:.4f}s")
    # print(f"File Check:       {file_check_duration:.4f}s", file=sys.stderr)
    log_message(f"File Check:       {file_check_duration:.4f}s")
    # print(f"Server Req:       {request_duration:.4f}s", file=sys.stderr)
    log_message(f"Server Req:       {request_duration:.4f}s")
    # print(f"XCLIP Copy:       {copy_duration:.4f}s", file=sys.stderr)
    log_message(f"XCLIP Copy:       {copy_duration:.4f}s")
    # print(f"Notify Copy:      {notify_copy_duration:.4f}s", file=sys.stderr)
    log_message(f"Notify Copy:      {notify_copy_duration:.4f}s")
    # print(f"WAV Delete:       {wav_delete_duration:.4f}s", file=sys.stderr)
    log_message(f"WAV Delete:       {wav_delete_duration:.4f}s")
    # print(f"Total Stop Func:  {total_stop_duration:.4f}s", file=sys.stderr)
    log_message(f"Total Stop Func:  {total_stop_duration:.4f}s")
    # print(f"----------------------------- ", file=sys.stderr)
    log_message(f"----------------------------- ")


def start_recording():
    """Starts the arecord process in the background."""
    # notify("Starting recording...", 1500)
    # print("Starting recording...")
    log_message("Starting recording...")

    # Create a temporary file that persists until manually deleted
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            wav_filename = tmp_wav.name
        # print(f"Recording to temporary file: {wav_filename}")
        log_message(f"Recording to temporary file: {wav_filename}")
    except Exception as e:
        # notify(f"Error creating temp file: {e}", 5000)
        # print(f"Error creating temp file: {e}", file=sys.stderr)
        log_message(f"Error creating temp file: {e}")
        sys.exit(1)

    # Command to record indefinitely until stopped
    record_cmd = [
        "arecord",
        "-q",  # Quiet mode
        "-D",
        "default",
        "-f",
        "S16_LE",
        "-r",
        str(SAMPLE_RATE),
        "-t",
        "wav",
        wav_filename,  # Record directly to the temp file
    ]

    try:
        # Start arecord in the background, hide its output
        process = subprocess.Popen(
            record_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        pid = process.pid
        # print(f"arecord started in background (PID: {pid})")
        log_message(f"arecord started in background (PID: {pid})")
    except FileNotFoundError:
        # notify("Error: arecord command not found.", 5000)
        # print("Error: arecord command not found.", file=sys.stderr)
        log_message("Error: arecord command not found.")
        # Clean up the created temp file
        if "wav_filename" in locals() and os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)
    except Exception as e:
        # notify(f"Error starting arecord: {e}", 5000)
        # print(f"Error starting arecord: {e}", file=sys.stderr)
        log_message(f"Error starting arecord: {e}")
        if "wav_filename" in locals() and os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)

    # Create the state file
    state = {"pid": pid, "wav_file": wav_filename}
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f)
        # print(f"State file created: {STATE_FILE_PATH}")
        log_message(f"State file created: {STATE_FILE_PATH}")
        # notify("Recording... Press shortcut again to stop.", 3000)
    except IOError as e:
        # notify(f"Error writing state file: {e}", 5000)
        # print(f"Error writing state file {STATE_FILE_PATH}: {e}", file=sys.stderr)
        log_message(f"Error writing state file {STATE_FILE_PATH}: {e}")
        # Attempt to kill the process we just started
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as kill_e:
            # print(f"Also failed to kill stray arecord process {pid}: {kill_e}", file=sys.stderr)
            log_message(f"Also failed to kill stray arecord process {pid}: {kill_e}")
        # Clean up temp file
        if os.path.exists(wav_filename):
            os.remove(wav_filename)
        sys.exit(1)


def main():
    # Check if recording is already in progress
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
            # notify("Error reading state file. Cleaning up.", 4000)
            # print(f"Error reading state file {STATE_FILE_PATH}: {e}. Attempting cleanup.",
            #       file=sys.stderr,
            #   )
            log_message(
                f"Error reading state file {STATE_FILE_PATH}: {e}. Attempting cleanup."
            )
            # Attempt to remove potentially corrupt state file
            try:
                os.remove(STATE_FILE_PATH)
            except OSError as remove_e:
                # print(f"Failed to remove corrupt state file: {remove_e}", file=sys.stderr)
                log_message(f"Failed to remove corrupt state file: {remove_e}")
                sys.exit(1)
    else:
        log_message("State file NOT found. Attempting to start recording.")
        start_recording()


if __name__ == "__main__":
    # --- Script Entry Point ---
    # Try logging immediately to see if script starts
    # Note: If log file creation fails initially, this might go to stderr
    script_start_success = False
    try:
        log_message("Script execution started.")
        script_start_success = True
    except Exception as log_init_e:
        log_message(f"Initial log message failed: {log_init_e}")  # Log init error

    # Basic locking to prevent issues if shortcut is triggered rapidly
    lock_file_path = "/tmp/stt_copy_lock"
    lock_acquired = False
    if script_start_success:
        try:
            log_message("Attempting to acquire lock...")
            # Try to create lock file exclusively
            fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            log_message(f"os.open succeeded (fd: {fd})")
            os.close(fd)
            log_message("os.close succeeded")
            lock_acquired = True
            log_message("Lock acquired successfully.")
        except FileExistsError:
            log_message("Script is already running (lock file exists). Exiting.")
            # notify("STT script already active.", 1000)
            sys.exit(1)
        except Exception as e:
            log_message(f"ERROR: Failed to create lock file {lock_file_path}: {e}")
            # Proceed cautiously without lock? Or exit? Let's exit for safety.
            sys.exit(1)
    else:
        # Fallback if initial logging failed
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
            # Ensure lock file is removed
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

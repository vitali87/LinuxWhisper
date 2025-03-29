# Linux Whisper STT Utility

A simple Speech-to-Text utility for Linux that allows you to:

1.  Press a keyboard shortcut (e.g., `Ctrl+Spacebar`) to start recording audio from your default microphone.
2.  Press the same shortcut again to stop recording.
3.  The recorded audio is sent to a self-hosted [Whisper](https://github.com/openai/whisper) FastAPI server running locally.
4.  The server transcribes the audio to text.
5.  The transcribed text is automatically copied to your system clipboard (`xclip`).

This provides a fast, local way to dictate text without relying on external cloud services after the initial model download.

**Note:** This utility has been developed and tested primarily on **Kali Linux (with Zsh)**. While it relies on standard Linux tools (`arecord`, `xclip`) and Python libraries, behavior on other distributions or desktop environments may vary. Use on other systems is possible but may require adjustments.

## Dependencies

### System Dependencies

You need the following command-line tools installed:

*   **`git`**: For cloning the repository.
*   **`arecord`**: Part of the `alsa-utils` package on most Debian/Ubuntu based systems. Used for recording audio.
    ```bash
    sudo apt update && sudo apt install alsa-utils git
    ```
*   **`xclip`**: Used for copying text to the clipboard.
    ```bash
    sudo apt install xclip
    ```
*   **(Optional but Recommended) `uv`**: A fast Python package installer/resolver. If not using `uv`, you can use standard `pip`.
    See [uv installation guide](https://github.com/astral-sh/uv#installation).

### Python Dependencies

*   Python 3.8+ recommended.
*   Packages listed in `requirements.txt`.

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/vitali87/LinuxWhisper.git
    cd LinuxWhisper
    ```

2.  **Create a Python Virtual Environment:**
    ```bash
    python -m venv .venv
    ```

3.  **Activate the Virtual Environment:**
    *   **Bash/Zsh:**
        ```bash
        source .venv/bin/activate
        ```
    *   **Fish:**
        ```bash
        source .venv/bin/activate.fish
        ```
    *(You should see `(.venv)` at the beginning of your terminal prompt)*

4.  **Install Python Dependencies:**
    *   **Using `uv` (Recommended):**
        ```bash
        uv pip install -r requirements.txt
        ```
    *   **Using `pip`:**
        ```bash
        pip install -r requirements.txt
        ```
    *(This will download the Whisper model chosen in `whisper_server.py` the first time the server runs, if not already cached)*

5.  **Run the Whisper Server:**
    *   Keep the virtual environment activated.
    *   Open a terminal in the project directory (`LinuxWhisper`).
    *   Run the server:
        ```bash
        python whisper_server.py
        ```
    *   Leave this terminal running in the background. It needs to stay running for the transcription shortcut to work. You should see output indicating the model is loading and the server is listening (e.g., on `http://127.0.0.1:8001`).

6.  **Configure Keyboard Shortcut:**
    *   Open your Linux desktop environment's keyboard shortcut settings (e.g., in GNOME, KDE, XFCE settings).
    *   Create a **new custom shortcut**.
    *   Set the desired key combination (e.g., `Ctrl+Spacebar`).
    *   Set the **command** to execute the `stt_copy.py` script using the Python interpreter from your virtual environment. **Make sure to use the absolute path:**
        ```
        /absolute/path/to/LinuxWhisper/.venv/bin/python /absolute/path/to/LinuxWhisper/stt_copy.py
        ```
        *(Replace `/absolute/path/to/LinuxWhisper` with the actual full path to where you cloned the repository, e.g., `/home/vitali/Documents/stt` in the original example)*.
    *   Save the shortcut.

## Usage

1.  Ensure the `whisper_server.py` script is running in a terminal.
2.  Press your configured shortcut (e.g., `Ctrl+Spacebar`) once to **start** recording.
3.  Speak clearly into your microphone.
4.  Press the same shortcut again to **stop** recording.
5.  Wait briefly (usually 1-2 seconds depending on recording length and CPU speed).
6.  The transcribed text will be automatically copied to your clipboard.
7.  Paste the text wherever you need it (e.g., `Ctrl+V`).

## Troubleshooting & Notes

*   **Microphone Input:** Ensure `arecord` is using your desired microphone. You might need to configure ALSA or PulseAudio settings if recording fails or is silent. Use `arecord -L` to list devices.
*   **Performance:** The `tiny.en` model is used by default for speed. Larger models (`base.en`, `small.en`, etc., configured in `whisper_server.py`) are more accurate but significantly slower. Transcription speed depends heavily on your CPU (or GPU if configured with CUDA).
*   **Compatibility:** Tested on Kali Linux. Usage on other Linux distributions might require adjustments to ALSA/PulseAudio configuration or shortcut command paths.
*   **Logging:** Debug logs are written to `/tmp/stt_copy_debug.log` (client script) and `/tmp/whisper_server_debug.log` (server script). Check these files if you encounter issues.
*   **Lock/State Files:** The script uses `/tmp/stt_copy_lock` and `/tmp/stt_recording_state.json`. If the script crashes, you might need to manually delete these files before it will start again (`rm -f /tmp/stt_copy_lock /tmp/stt_recording_state.json`).
*   **Server Port:** The server runs on port `8001`. If this conflicts, change the `PORT` variable in `whisper_server.py` and the `SERVER_URL` in `stt_copy.py`. 
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
*   Python 3.12 is recommended and tested.
*   Packages listed in `requirements.txt`.

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/vitali87/LinuxWhisper.git
    cd LinuxWhisper
    ```

2.  **Create a Python Virtual Environment using `uv`:**
    ```bash
    # Ensure you have Python 3.12 available in your system path
    uv venv -p 3.12 .venv
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

4.  **Configure Settings:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file to adjust settings if needed (e.g., change `WHISPER_MODEL_NAME`, temporary file paths, server port).
        The defaults should work for most basic setups.

5.  **Install Python Dependencies:**
    *   Ensure your virtual environment is active.
    *   **Using `uv` (Recommended):**
        ```bash
        uv pip install -r requirements.txt
        ```
    *   **Using `pip`:**
        ```bash
        pip install -r requirements.txt
        ```
    *(This installs necessary libraries like `requests`, `fastapi`, `openai-whisper`, and `python-dotenv`)*

6.  **Run the Whisper Server:**
    *   Keep the virtual environment activated.
    *   Open a terminal in the project directory (`LinuxWhisper`).
    *   Run the server:
        ```bash
        python whisper_server.py
        ```
    *   Leave this terminal running in the background. It needs to stay running for the transcription shortcut to work. You should see output indicating the model is loading and the server is listening (e.g., on `http://127.0.0.1:8001`).

7.  **Configure Keyboard Shortcut:**
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
*   **Server Port:** The server runs on the port specified by `WHISPER_SERVER_PORT` in your `.env` file (default `8001`). If this conflicts, change it in `.env`.
*   **Configuration:** Most settings like model name, server address, temporary file paths, etc., can be adjusted in the `.env` file.

## .env Configuration

The `.env` file contains several configuration options:

*   **`WHISPER_MODEL_NAME`**: This is the name of the Whisper model to be used.
*   **`WHISPER_SERVER_PORT`**: This is the port on which the server will run.
*   **`TEMP_DIR`**: This is the directory where temporary files will be stored.
*   **`SERVER_URL`**: This is the URL of the server.
*   **`LOG_LEVEL`**: This is the level of logging to be used.

You can edit these options in the `.env` file to suit your needs. 
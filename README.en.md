# RB Terminal

SSH terminal with integrated AI agent. The AI executes commands, analyzes outputs, and iterates until task completion.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

On first run, click the **Config** button in the toolbar to configure:
- **API Key:** Your OpenRouter key
- **Model:** Select from the list of available models

Settings are saved to `%APPDATA%\.rb-terminal\settings.json`

## Usage

```bash
python main.py
```

## Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+H` | Toggle hosts sidebar |
| `Ctrl+J` | Toggle AI chat |
| `Ctrl+N` | Quick connect |
| `Ctrl+D` | Disconnect |
| `R` | Reconnect (when disconnected) |
| `Ctrl+V` | Paste in terminal |
| `Shift+Insert` | Paste in terminal |
| `Right-click` | Paste in terminal |
| `Ctrl+Scroll` | Zoom (increase/decrease font) |
| `Ctrl++` / `Ctrl+-` | Zoom |
| `Ctrl+0` | Reset zoom |

**Text selection:** Selecting text with the mouse automatically copies to clipboard (PuTTY-style).

## Stack

- **GUI:** PySide6
- **SSH:** asyncssh
- **LLM:** OpenRouter API
- **Encryption:** Fernet

## Build

```bash
pyinstaller --onefile --windowed main.py
```

## License

MIT

# RB Terminal

SSH terminal with integrated AI agent. The AI executes commands, analyzes outputs, and iterates until task completion.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy the example file and add your API key:

```bash
cp config/settings.example.json config/settings.json
```

Edit `config/settings.json`:
```json
{
  "openrouter_api_key": "your-openrouter-key",
  "default_model": "google/gemini-2.5-flash",
  "theme": "dark"
}
```

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
| `R` | Reconnect |

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

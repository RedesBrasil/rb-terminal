# RB Terminal

Terminal SSH com agente IA integrado. A IA executa comandos, analisa saídas e itera até completar a tarefa.

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Copie o arquivo de exemplo e adicione sua API key:

```bash
cp config/settings.example.json config/settings.json
```

Edite `config/settings.json`:
```json
{
  "openrouter_api_key": "sua-chave-openrouter",
  "default_model": "google/gemini-2.5-flash",
  "theme": "dark"
}
```

## Uso

```bash
python main.py
```

## Atalhos

| Tecla | Ação |
|-------|------|
| `Ctrl+H` | Toggle sidebar hosts |
| `Ctrl+J` | Toggle chat IA |
| `Ctrl+N` | Conexão rápida |
| `Ctrl+D` | Desconectar |
| `R` | Reconectar |

## Stack

- **GUI:** PySide6
- **SSH:** asyncssh
- **LLM:** OpenRouter API
- **Criptografia:** Fernet

## Build

```bash
pyinstaller --onefile --windowed main.py
```

## Licença

MIT

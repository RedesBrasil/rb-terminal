# RB Terminal

> [English version](README.en.md)

Terminal SSH com agente IA integrado. A IA executa comandos, analisa saídas e itera até completar a tarefa.

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Na primeira execução, clique no botão **Config** na toolbar para configurar:
- **API Key:** Sua chave do OpenRouter
- **Modelo:** Selecione da lista de modelos disponíveis

As configurações são salvas em `%APPDATA%\.rb-terminal\settings.json`

## Uso

```bash
python main.py
```

## Atalhos

| Tecla | Ação |
|-------|------|
| `Ctrl+H` | Toggle sidebar hosts |
| `Ctrl+I` | Toggle chat IA |
| `Ctrl+N` | Conexão rápida |
| `Ctrl+D` | Desconectar |
| `R` | Reconectar (quando desconectado) |
| `Ctrl+V` | Colar no terminal |
| `Shift+Insert` | Colar no terminal |
| `Clique direito` | Colar no terminal |
| `Ctrl+Scroll` | Zoom (aumentar/diminuir fonte) |
| `Ctrl++` / `Ctrl+-` | Zoom |
| `Ctrl+0` | Resetar zoom |

**Seleção de texto:** Selecionar texto com o mouse copia automaticamente para a área de transferência (estilo PuTTY).

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

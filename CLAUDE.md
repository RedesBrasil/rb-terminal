# RB Terminal

Terminal SSH desktop com agente IA integrado. A IA executa comandos no dispositivo remoto, lê saídas, raciocina e continua iterando até completar a tarefa.

## Stack

| Componente      | Tecnologia              |
|-----------------|-------------------------|
| Linguagem       | Python 3.11+            |
| GUI             | PySide6                 |
| LLM Provider    | OpenRouter              |
| SSH             | asyncssh                |
| Terminal        | pyte (emulação VT100)   |
| Criptografia    | cryptography (Fernet)   |
| Persistência    | JSON local              |
| Async           | qasync (Qt + asyncio)   |

## Estrutura do Projeto

```
rb-terminal/
├── main.py                     # Entry point (--debug para logs detalhados)
├── core/
│   ├── agent.py                # Agente IA com OpenRouter API
│   ├── ssh_session.py          # Wrapper asyncssh com PTY
│   ├── hosts.py                # CRUD hosts (modelo + persistência JSON)
│   ├── crypto.py               # Criptografia de senhas (Fernet)
│   ├── settings.py             # Gerenciador de configurações (singleton)
│   └── device_types.py         # Gerenciador de tipos de dispositivos
├── gui/
│   ├── main_window.py          # Janela principal com hosts view + abas + chat
│   ├── terminal_widget.py      # Widget terminal com emulação ANSI
│   ├── tab_session.py          # Dataclass TabSession (estado por aba)
│   ├── chat_widget.py          # Widget chat IA
│   ├── hosts_view.py           # Tela principal de hosts (cards/lista)
│   ├── host_card.py            # Widgets de card e item de lista
│   ├── tags_widget.py          # Widget de tags com autocomplete
│   ├── hosts_dialog.py         # Dialogs de hosts
│   └── settings_dialog.py      # Dialog de configurações
├── config/
│   └── settings.json           # Configurações fallback
└── requirements.txt
```

## Arquivos de Dados

Salvos em `~/.rb-terminal/` (ou `%APPDATA%\.rb-terminal` no Windows):

- `hosts.json` - Hosts salvos com senhas criptografadas
- `device_types.json` - Tipos de dispositivos customizados
- `settings.json` - Configurações do usuário (API key, modelo, chat_position, available_tags, hosts_view_mode, hosts_sort_by)
- `.key` - Chave Fernet

## Componentes Principais

### core/agent.py

Agente IA que executa comandos SSH via OpenRouter API. Recebe função `execute_command` async, callbacks para status e contexto de `device_type`. Fluxo agêntico: Mensagem → IA decide tool call → Executa SSH → IA analisa output → Loop até resposta final.

### core/ssh_session.py

Wrapper asyncssh com PTY. `SSHConfig` define host, port, username, password, terminal_type, dimensões. `SSHSession` recebe config, output_callback e disconnect_callback. Features: auto-resposta a terminal queries, detecção de desconexão, autenticação interativa.

### core/settings.py

Singleton `get_settings_manager()` para configurações com persistência. Métodos: `get_api_key()`, `get_model()`, `set_api_key()`, `get_tags()`, `add_tag()`, `save()`.

### core/hosts.py

Modelo `Host` com campos: id, name, host, port, username, password_encrypted, terminal_type, device_type, tags, created_at. `HostsManager` para CRUD.

### gui/tab_session.py

Dataclass `TabSession` encapsula estado de cada aba: id (UUID), terminal, ssh_session, agent, config (para reconexão), pending_connection, host_id, host_name, device_type, output_buffer, connection_status.

### gui/main_window.py

Arquitetura: `QStackedWidget` alterna entre `HostsView` (index 0) e área de terminal (index 1). `_sessions: Dict[str, TabSession]` por tab_id, `_tab_widget: QTabWidget`. Signals thread-safe: `_ssh_output_received(tab_id, data)`, `_unexpected_disconnect(tab_id)`. Fluxo de conexão: `_connect_to_host()` → `_initiate_connection_for_session()` → `_connect_session_async()` → `_create_agent_for_session()`.

### gui/terminal_widget.py

Widget de terminal com emulação pyte (VT100/xterm). Signals: `input_entered`, `reconnect_requested`, `prelogin_credentials`, `prelogin_cancelled`. Flags: `_disconnected_mode`, `_has_content`, `_prelogin_mode`.

## Notas Técnicas

1. **Async:** Todo código SSH/IA deve ser async (qasync integra Qt + asyncio)
2. **Thread-safety:** Usar Qt Signals para comunicação entre threads
3. **Output buffering:** SSH output é bufferizado (10ms) antes de renderizar
4. **Reconexão:** `session.config` guarda última config para reconexão com R
5. **Terminal queries:** Respondidas automaticamente nos primeiros 5s de conexão

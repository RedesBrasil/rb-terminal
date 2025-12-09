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
| Criptografia    | cryptography (PBKDF2)   |
| Persistência    | JSON local unificado    |
| Async           | qasync (Qt + asyncio)   |

## Estrutura do Projeto

```
rb-terminal/
├── main.py                     # Entry point (--debug para logs detalhados)
├── core/
│   ├── agent.py                # Agente IA com OpenRouter API
│   ├── ssh_session.py          # Wrapper asyncssh com PTY
│   ├── sftp_manager.py         # Operações SFTP async (download, upload, list)
│   ├── data_manager.py         # Gerenciador unificado de dados (singleton)
│   ├── crypto.py               # Criptografia PBKDF2 + master password
│   ├── hosts.py                # [LEGADO] Mantido para referência
│   ├── settings.py             # [LEGADO] Mantido para referência
│   └── device_types.py         # Gerenciador de tipos de dispositivos
├── gui/
│   ├── main_window.py          # Janela principal com hosts view + abas + chat
│   ├── terminal_widget.py      # Widget terminal com emulação ANSI
│   ├── file_browser.py         # File browser SFTP lateral
│   ├── tab_session.py          # Dataclass TabSession (estado por aba)
│   ├── chat_widget.py          # Widget chat IA
│   ├── hosts_view.py           # Tela principal de hosts (cards/lista/tabela)
│   ├── host_card.py            # HostCard, HostListItem, HostsTableWidget
│   ├── fields_config_dialog.py # Dialog para configurar campos visíveis
│   ├── tags_widget.py          # Widget de tags com autocomplete
│   ├── hosts_dialog.py         # Dialogs de hosts
│   ├── settings_dialog.py      # Dialog de configurações
│   ├── setup_dialog.py         # Dialog de primeira execução
│   ├── unlock_dialog.py        # Dialog de desbloqueio
│   ├── change_password_dialog.py # Dialog para alterar senha mestra
│   └── export_import_dialogs.py  # Dialogs de exportação/importação
├── config/
│   └── settings.json           # Configurações fallback
└── requirements.txt
```

## Arquivos de Dados

Salvos em `~/.rb-terminal/` (ou `%APPDATA%\.rb-terminal` no Windows):

- `data.json` - Arquivo unificado com hosts, settings e config de segurança
- `pointer.json` - Aponta para localização customizada do data.json (ex: Dropbox)
- `.session` - Cache da chave derivada para sessão atual
- `device_types.json` - Tipos de dispositivos customizados

### Estrutura do data.json

```json
{
  "version": "1.0",
  "security": {
    "has_master_password": true,
    "password_salt": "base64...",
    "password_hash": "base64..."
  },
  "settings": {
    "openrouter_api_key": "sk-...",
    "default_model": "google/gemini-2.5-flash",
    "max_agent_iterations": 10,
    "chat_position": "bottom",
    "sftp_position": "left",
    "available_tags": ["prod", "dev"],
    "hosts_view_mode": "cards",
    "hosts_sort_by": "name",
    "max_conversations_per_host": 10,
    "winbox_path": "C:/path/to/winbox64.exe",
    "card_visible_fields": ["name", "host", "tags", "device_type"],
    "list_visible_fields": ["name", "host", "port", "username", "tags", "device_type", "manufacturer"],
    "list_column_widths": {"host": 200, "port": 80},
    "ai_system_prompt": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_backup_enabled": false
  },
  "hosts": [
    {
      "id": "uuid",
      "name": "Router Principal",
      "hosts": ["192.168.1.1", "router.example.com", "2001:db8::1"],
      "host": "192.168.1.1",
      "port": 22,
      "username": "admin",
      "port_knocking": [
        {"protocol": "tcp", "port": 1234},
        {"protocol": "udp", "port": 5678}
      ],
      "winbox_port": 8291,
      "http_port": 80,
      "https_enabled": false
    }
  ],
  "conversations": [
    {
      "id": "uuid",
      "host_id": "host-uuid",
      "title": "Título gerado da primeira mensagem",
      "created_at": "2024-12-04T10:00:00",
      "updated_at": "2024-12-04T10:30:00",
      "messages": [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
      ],
      "prompt_tokens": 0,
      "completion_tokens": 0,
      "total_cost": 0.0
    }
  ]
}
```

## Componentes Principais

### core/data_manager.py

Singleton `get_data_manager()` que unifica hosts e settings. Gerencia:
- Criptografia com master password opcional (PBKDF2 600k iterações)
- Cache de sessão para evitar digitar senha toda vez
- Caminho customizável via pointer.json (sincronização Dropbox/OneDrive)
- Export/import com senha de proteção opcional
- Migração automática de arquivos legados
- Histórico de conversas de chat por host (com rotação automática)

### core/crypto.py

`CryptoManager` para criptografia PBKDF2. `LegacyCryptoManager` para migração de dados antigos (Fernet). Métodos principais: `encrypt()`, `decrypt()`, `hash_password()`, `verify_password()`.

### core/agent.py

Agente IA que executa comandos SSH via OpenRouter API. Fluxo agêntico: Mensagem → IA decide tool call → Executa SSH → IA analisa output → Loop até resposta final.

- `SSHAgent`: Classe principal. `DEFAULT_SYSTEM_PROMPT` é o prompt base, `TOOL_INSTRUCTION` é injetado automaticamente no final.
- `UsageStats`: Dataclass para tracking de tokens e custo (`prompt_tokens`, `completion_tokens`, `total_cost`).
- `_get_system_prompt()`: Monta prompt = (custom ou default) + dados do host + instrução da ferramenta.
- System prompt customizável via `ai_system_prompt` em settings (vazio = usar default).
- **Web Search:** Tool `web_search` disponível quando checkbox "Pesquisa na Web" está marcada. Usa OpenRouter com sufixo `:online` e plugin Exa. A IA decide autonomamente quando pesquisar.

### core/ssh_session.py

Wrapper asyncssh com PTY. `SSHConfig` define host, port, username, password, terminal_type, dimensões. `SSHSession` recebe config, output_callback e disconnect_callback. Features: auto-resposta a terminal queries, detecção de desconexão, autenticação interativa.

### core/sftp_manager.py

`SFTPManager` com operações async: `list_dir()`, `download()`, `upload()`, `download_directory()`, `upload_directory()`, `mkdir()`, `rename()`, `delete()`, `read_text()`, `write_text()`. Usa mesma conexão SSH via `asyncssh.SFTPClient`.

### gui/file_browser.py

`FileBrowser` widget lateral (Ctrl+E). Features: navegação de pastas, upload/download (arquivos e pastas), drag & drop bidirecional, edição remota de arquivos (abre no editor padrão, monitora mudanças, faz upload automático), "follow terminal folder". `RemoteFileEditor` gerencia arquivos em edição.

### gui/main_window.py

Arquitetura: `QStackedWidget` alterna entre `HostsView` (index 0) e área de terminal (index 1). `_sessions: Dict[str, TabSession]` por tab_id, `_tab_widget: QTabWidget`. Signals thread-safe: `_ssh_output_received(tab_id, data)`, `_unexpected_disconnect(tab_id)`. Fluxo de inicialização: `_handle_startup()` → SetupDialog ou UnlockDialog se necessário → `DataManager.load()`.

### gui/setup_dialog.py

Dialog de primeira execução. Permite escolher entre usar senha mestra (recomendado) ou continuar sem proteção.

### gui/unlock_dialog.py

Dialog para desbloquear quando há senha mestra mas sem sessão cacheada (novo computador ou sessão expirada).

### gui/settings_dialog.py

Dialog de configurações com QTabWidget:
- **Aba Geral:** API OpenRouter (key, modelo, iterações, posição chat), Armazenamento, Winbox.
- **Aba IA:** System prompt editável com preview. Dados do host e `TOOL_INSTRUCTION` são injetados automaticamente (não editáveis).
- **Aba Backup:** Abrir data.json, Export/Import, Telegram (token, chat_id, ativar backup automático).

## Notas Técnicas

1. **Async:** Todo código SSH/IA deve ser async (qasync integra Qt + asyncio)
2. **Thread-safety:** Usar Qt Signals para comunicação entre threads
3. **Output buffering:** SSH output é bufferizado (10ms) antes de renderizar
4. **Reconexão:** `session.config` guarda última config para reconexão com R
5. **Terminal queries:** Respondidas automaticamente nos primeiros 5s de conexão
6. **Segurança:** PBKDF2 com 600k iterações (OWASP 2024+), salt de 32 bytes
7. **Migração:** Arquivos legados (hosts.json, settings.json, .key) são migrados automaticamente
8. **Port Knocking:** Sequência de portas TCP/UDP acionadas antes da conexão SSH (fire and forget, sem esperar resposta)
9. **Winbox:** Menu de contexto do host lança `winbox.exe <ip>:<porta> <user> <senha>`. Porta padrão 8291, configurável por host. Port knocking executado antes se configurado.
10. **Acesso Web:** Menu de contexto abre navegador padrão com `http(s)://<ip>:<porta>`. Porta e HTTPS configuráveis por host em Opções Avançadas.
11. **Múltiplos IPs:** Cada host pode ter múltiplos endereços (IP local, público, IPv6, domínio). Campo `hosts` é lista, `host` é propriedade de compatibilidade que retorna o primeiro. Ao conectar: fallback automático entre IPs. Menu de contexto mostra submenu com todos os IPs disponíveis para SSH, Winbox e Web.
12. **Hosts View:** Modo cards (grid) ou lista (QTableWidget com QHeaderView nativo). Campos visíveis e ordem configuráveis via botão ☰. Colunas redimensionáveis com larguras persistidas. Ordenação por: name, host, port, username, device_type, manufacturer, os_version.
13. **System Prompt IA:** Estrutura: `[prompt editável] + [dados do host] + [TOOL_INSTRUCTION]`. O usuário edita só a primeira parte. Dados do host (nome, IP, tipo, fabricante, tags, notes) e instrução da ferramenta são injetados automaticamente em `_get_system_prompt()`.
14. **Usage Tracking:** `UsageStats` em agent.py rastreia tokens e custo. Custo real é buscado via `/generation?id=` após cada chamada. Estatísticas salvas por conversa em `data.json`.
15. **SFTP:** File browser lateral usa mesma conexão SSH. Posição configurável (left/right/bottom). Download de pasta mostra progresso como "X/Y arquivos (Z%)", arquivos individuais como "X.X/Y.Y KB ou MB (Z%)". Edição remota: arquivo baixado para temp, aberto no editor padrão, monitorado por `QTimer`, upload automático ao salvar.
16. **Telegram Backup:** Envia `data.json` para Telegram a cada `_save()`. Configurável em Settings > Backup. Campos: `telegram_bot_token`, `telegram_chat_id`, `telegram_backup_enabled`. Operações de conversa usam `skip_telegram_backup=True` para evitar spam. Caption inclui timestamp e hostname.
17. **Web Search:** Checkbox "Pesquisa na Web" no chat habilita tool `web_search` para a IA. Implementação em `_execute_web_search()` usa `model:online` com plugin Exa do OpenRouter. A IA decide quando usar baseado no contexto (quando usuário pede pesquisa ou informações atualizadas). Custo adicional: ~$0.02 por pesquisa (5 resultados).

## Build

Para compilar o executável Windows:

```bash
# Usando o script de build (recomendado)
build.bat

# Ou manualmente
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller build.spec --clean
```

O executável será gerado em `dist/RB-Terminal.exe`.

**Arquivos de build:**
- `build.bat` - Script Windows que instala dependências e compila
- `build.spec` - Configuração PyInstaller com hiddenimports necessários (pywin32, asyncssh, httpx, etc.)

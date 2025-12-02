# SSH AI Terminal

Terminal SSH desktop com agente IA integrado. A IA executa comandos no dispositivo remoto, le saidas, raciocina e continua iterando ate completar a tarefa - similar ao Claude Code, mas para administracao de redes/servidores.

## Stack

| Componente      | Tecnologia              |
|-----------------|-------------------------|
| Linguagem       | Python 3.11+            |
| GUI             | PySide6                 |
| LLM Provider    | OpenRouter              |
| SSH             | asyncssh                |
| Terminal Type   | xterm (fallback: vt100) |
| Criptografia    | cryptography (Fernet)   |
| Persistencia    | JSON local              |
| Build           | PyInstaller             |

## Estrutura do Projeto

```
ssh-ai-terminal/
├── main.py                     # Entry point
├── core/
│   ├── agent.py                # Agente IA com OpenRouter API
│   ├── ssh_session.py          # Wrapper asyncssh (conexao SSH)
│   ├── hosts.py                # CRUD hosts (modelo + persistencia JSON)
│   ├── crypto.py               # Criptografia de senhas (Fernet)
│   └── device_types.py         # Gerenciador de tipos de dispositivos
├── gui/
│   ├── main_window.py          # Janela principal com sidebar + terminal + chat
│   ├── terminal_widget.py      # Widget terminal com suporte ANSI
│   ├── chat_widget.py          # Widget chat IA
│   └── hosts_dialog.py         # Dialogs: HostDialog, PasswordPromptDialog, QuickConnectDialog
├── config/
│   └── settings.json           # API key OpenRouter, modelo padrao
└── requirements.txt
```

## Arquivos de Dados

Salvos em `~/.ssh-ai-terminal/` (ou `%APPDATA%` no Windows):

- `hosts.json` - Lista de hosts salvos com senhas criptografadas
- `device_types.json` - Tipos de dispositivos customizados
- `.key` - Chave Fernet para criptografia

## Componentes Principais

### core/agent.py

Agente IA que executa comandos SSH via OpenRouter API.

```python
# Criar agente
agent = create_agent(
    execute_command=async_ssh_function,
    on_command_executed=callback_cmd_output,
    on_thinking=callback_status,
    device_type="MikroTik"  # Contexto para a IA
)

# Enviar mensagem
response = await agent.chat("Configure OSPF na ether2")
```

**Fluxo agentico:**
1. Usuario envia mensagem
2. IA analisa e decide executar comando via tool `execute_command`
3. Comando executado no SSH, output retornado para IA
4. IA analisa output, decide proximo passo
5. Loop continua ate IA responder sem tool calls

**Device Type Context:**
A IA recebe contexto do tipo de dispositivo conectado:
- `Linux` -> Comandos bash, systemctl, ip
- `MikroTik` -> Comandos RouterOS
- `Huawei` -> Comandos Huawei CLI
- `Cisco` -> Comandos Cisco IOS
- Tipos customizados -> Mensagem generica

### core/hosts.py

Modelo `Host` e `HostsManager` para CRUD de hosts.

```python
@dataclass
class Host:
    id: str
    name: str
    host: str
    port: int = 22
    username: str = ""
    password_encrypted: Optional[str] = None
    terminal_type: str = "xterm"      # xterm ou vt100
    device_type: Optional[str] = None  # Linux, MikroTik, Huawei, Cisco, ou custom
    created_at: str
```

### core/device_types.py

Gerencia tipos de dispositivos com suporte a tipos customizados.

```python
manager = get_device_types_manager()

# Tipos padrao: Linux, MikroTik, Huawei, Cisco
all_types = manager.get_all()

# Adicionar tipo customizado (salvo em device_types.json)
manager.add_custom("FortiGate")

# Garantir que tipo existe (adiciona se nao existir)
manager.ensure_exists("PFSense")
```

### core/ssh_session.py

Wrapper asyncssh com PTY para terminal interativo.

```python
config = SSHConfig(
    host="192.168.1.1",
    port=22,
    username="admin",  # Opcional - pedido no terminal se vazio
    password="senha",  # Opcional - pedido no terminal se vazio
    terminal_type="xterm",
    term_width=80,
    term_height=24
)

# Callback opcional para desconexao inesperada
session = SSHSession(config, on_output_callback, on_disconnect_callback)
await session.connect()
await session.send_input("ls -la\n")
output = await session.execute_command("uname -a")  # Para agente IA
await session.disconnect()
```

**Autenticacao interativa (estilo PuTTY):**
- Username e password sao opcionais ao cadastrar host ou conexao rapida
- Se nao informados, o servidor SSH pede via keyboard-interactive auth
- Prompts de login/senha aparecem diretamente no terminal
- Se credenciais estiverem salvas, conecta automaticamente

**Deteccao de desconexao:**
- `disconnect_callback` - Callback chamado quando conexao e perdida inesperadamente
- Detecta EOF, `ChannelClosedError`, `ConnectionLost`, `BrokenPipeError`
- `_manual_disconnect` flag diferencia desconexao manual vs inesperada

### gui/main_window.py

Janela principal com:
- Sidebar colapsavel com lista de hosts
- Terminal SSH central
- Chat IA no rodape (toggle com Ctrl+J)
- Toolbar com acoes

**Atalhos:**
- `Ctrl+H` - Toggle sidebar hosts
- `Ctrl+J` - Toggle chat IA
- `Ctrl+N` - Conexao rapida
- `Ctrl+D` - Desconectar
- `R` - Reconectar (quando desconectado)

**Reconexao automatica:**
- Quando conexao e perdida inesperadamente, terminal mostra "Pressione R para reconectar"
- Ultima config de conexao e salva em `_last_config`
- Signal `_unexpected_disconnect` notifica desconexao via Qt signal (thread-safe)
- Desconexao manual (botao) limpa `_last_config`, nao permite reconectar com R

### gui/terminal_widget.py

Widget de terminal com emulacao VT100/xterm via pyte.

**Signals:**
- `input_entered(str)` - Emitido quando usuario digita
- `reconnect_requested()` - Emitido quando usuario pressiona R no modo desconectado

**Modo desconectado:**
- `_disconnected_mode` flag ativa modo especial
- `show_disconnected_message()` limpa terminal e mostra mensagem centralizada
- No modo desconectado, apenas tecla R e capturada

### gui/hosts_dialog.py

Tres dialogs:
- `HostDialog` - Adicionar/editar host
- `PasswordPromptDialog` - Pedir senha ao conectar
- `QuickConnectDialog` - Conexao rapida sem salvar

## Configuracao

### config/settings.json

```json
{
  "openrouter_api_key": "sk-or-v1-...",
  "default_model": "google/gemini-2.5-flash",
  "theme": "dark"
}
```

### Exemplo hosts.json

```json
{
  "hosts": [
    {
      "id": "uuid-1234",
      "name": "Mikrotik Principal",
      "host": "192.168.1.1",
      "port": 22,
      "username": "admin",
      "password_encrypted": "gAAAAA...",
      "terminal_type": "xterm",
      "device_type": "MikroTik",
      "created_at": "2025-01-15T10:00:00"
    }
  ]
}
```

## Fluxo do Usuario

1. Abre app -> ve lista de hosts salvos
2. Duplo clique no host -> conecta SSH:
   - Se tem credenciais salvas -> conecta automaticamente
   - Se nao tem -> terminal pede usuario/senha (estilo PuTTY)
3. Se conexao cair -> terminal mostra "Pressione R para reconectar"
4. Usa terminal normalmente OU abre chat IA (Ctrl+J)
5. No chat: "Mostre o uso de CPU" -> IA executa comandos apropriados
6. Usuario ve comandos executados no terminal em tempo real
7. IA responde com analise apos completar

## Desenvolvimento

### Requisitos

```bash
pip install -r requirements.txt
```

Principais dependencias:
- PySide6
- asyncssh
- qasync (Qt + asyncio)
- httpx
- cryptography

### Executar

```bash
python main.py
```

### Build Windows

```bash
pyinstaller --onefile --windowed main.py
```

## Funcionalidades Pendentes (v2)

- [ ] SFTP file browser
- [ ] Multiplas sessoes em abas
- [ ] Historico de chat persistido
- [ ] Suporte a chaves SSH
- [ ] Lista de comandos perigosos configuravel
- [ ] Timeout de comandos configuravel

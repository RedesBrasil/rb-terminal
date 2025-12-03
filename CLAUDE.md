# RB Terminal

Terminal SSH desktop com agente IA integrado. A IA executa comandos no dispositivo remoto, le saidas, raciocina e continua iterando ate completar a tarefa - similar ao Claude Code, mas para administracao de redes/servidores.

## Stack

| Componente      | Tecnologia              |
|-----------------|-------------------------|
| Linguagem       | Python 3.11+            |
| GUI             | PySide6                 |
| LLM Provider    | OpenRouter              |
| SSH             | asyncssh                |
| Terminal Type   | xterm (default), xterm-256color, vt100 |
| Criptografia    | cryptography (Fernet)   |
| Persistencia    | JSON local              |
| Build           | PyInstaller             |

## Estrutura do Projeto

```
rb-terminal/
├── main.py                     # Entry point (suporta --debug para logs detalhados)
├── core/
│   ├── agent.py                # Agente IA com OpenRouter API
│   ├── ssh_session.py          # Wrapper asyncssh (conexao SSH)
│   ├── hosts.py                # CRUD hosts (modelo + persistencia JSON)
│   ├── crypto.py               # Criptografia de senhas (Fernet)
│   ├── settings.py             # Gerenciador de configuracoes (singleton)
│   └── device_types.py         # Gerenciador de tipos de dispositivos
├── gui/
│   ├── main_window.py          # Janela principal com sidebar + terminal + chat
│   ├── terminal_widget.py      # Widget terminal com suporte ANSI
│   ├── chat_widget.py          # Widget chat IA
│   ├── hosts_dialog.py         # Dialogs: HostDialog, PasswordPromptDialog, QuickConnectDialog
│   └── settings_dialog.py      # Dialog de configuracoes (API key, modelo LLM)
├── config/
│   └── settings.json           # API key OpenRouter, modelo padrao (fallback)
└── requirements.txt
```

## Arquivos de Dados

Salvos em `~/.rb-terminal/` (ou `%APPDATA%\.rb-terminal` no Windows):

- `hosts.json` - Lista de hosts salvos com senhas criptografadas
- `device_types.json` - Tipos de dispositivos customizados
- `settings.json` - Configuracoes do usuario (API key, modelo padrao)
- `.key` - Chave Fernet para criptografia

## Componentes Principais

### main.py

Entry point da aplicacao com suporte a argumentos de linha de comando.

**Argumentos:**
- `--debug`: Ativa modo debug com logs detalhados (DEBUG level)
- Sem argumentos: Modo normal com logs INFO

**Exemplo de uso:**
```bash
# Modo normal
python main.py

# Modo debug (troubleshooting)
python main.py --debug
```

**Funcionalidades:**
- Configura logging (INFO ou DEBUG)
- Inicializa QApplication (Qt)
- Cria event loop integrado Qt + asyncio (qasync)
- Instancia MainWindow
- Trata KeyboardInterrupt gracefully

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

### core/settings.py

Gerenciador centralizado de configuracoes com persistencia.

```python
from core.settings import get_settings_manager

# Singleton - mesma instancia em toda aplicacao
manager = get_settings_manager()

# Ler configuracoes
api_key = manager.get_api_key()
model = manager.get_model()

# Alterar configuracoes
manager.set_api_key("sk-or-v1-...")
manager.set_model("anthropic/claude-3-opus")

# Salvar para disco
manager.save()

# Recarregar do disco
manager.reload()
```

**Prioridade de carregamento:**
1. `%APPDATA%\.rb-terminal\settings.json` (usuario)
2. Bundled config (PyInstaller)
3. `config/settings.json` (desenvolvimento)

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
    terminal_type: str = "xterm"      # Default: xterm. Opcoes: xterm-256color, vt100
    device_type: Optional[str] = None  # Linux, MikroTik, Huawei, Cisco, ou custom
    disable_terminal_detection: bool = False  # Deprecated - sempre False para novos hosts
    created_at: str

    def get_effective_username(self) -> str:
        # Retorna username com sufixo +ct se disable_terminal_detection=True
        # Nota: Este campo e mantido apenas para retrocompatibilidade
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

**Cores ANSI em MikroTik:**
- MikroTik envia queries de terminal (DA1, DA2) para detectar capacidades antes de habilitar cores
- `_respond_to_terminal_queries_async()` responde automaticamente com respostas VT220
- Se nao funcionar, usar `disable_terminal_detection=True` no Host (adiciona sufixo `+ct` ao username)
- Sufixo `+ct` desabilita deteccao de terminal no MikroTik, forcando modo sem cores nativas

### gui/main_window.py

Janela principal com:
- Sidebar colapsavel com lista de hosts
- Terminal SSH central
- Chat IA no rodape (toggle com Ctrl+I)
- Toolbar com acoes (Config, Conexao Rapida)

**Atalhos:**
- `Ctrl+H` - Toggle sidebar hosts
- `Ctrl+I` - Toggle chat IA
- `Ctrl+N` - Conexao rapida
- `Ctrl+D` - Desconectar
- `R` - Reconectar (quando desconectado)

**Reconexao automatica:**
- Quando conexao e perdida (exit, timeout, etc), pressionar `R` reconecta ao mesmo host
- Ultima config de conexao e salva em `_last_config`
- Signal `_unexpected_disconnect` notifica desconexao via Qt signal (thread-safe)
- Desconexao manual limpa `_last_config`, nao permite reconectar com R

### gui/terminal_widget.py

Widget de terminal com emulacao VT100/xterm via pyte.

**Signals:**
- `input_entered(str)` - Emitido quando usuario digita
- `reconnect_requested()` - Emitido quando usuario pressiona R no modo desconectado

**Selecao e Clipboard (estilo PuTTY):**
- Selecionar texto com mouse copia automaticamente para clipboard
- Colar com `Ctrl+V`, `Shift+Insert`, ou clique direito do mouse

**Zoom:**
- `Ctrl+Scroll` - Aumentar/diminuir fonte
- `Ctrl++` / `Ctrl+-` - Aumentar/diminuir fonte
- `Ctrl+0` - Resetar zoom para tamanho padrao
- Range de fonte: 6-32pt

**Modo desconectado:**
- `_disconnected_mode` flag ativa modo especial
- `show_disconnected_message()` limpa terminal e mostra mensagem centralizada
- No modo desconectado, apenas tecla R e capturada

### gui/settings_dialog.py

Dialog para configurar API key e modelo LLM.

```python
from gui.settings_dialog import SettingsDialog

dialog = SettingsDialog(parent)
if dialog.exec() == QDialog.Accepted:
    # Configuracoes salvas automaticamente
    pass
```

**Funcionalidades:**
- Campo API Key com toggle mostrar/esconder
- Lista de modelos buscada da API OpenRouter em tempo real
- Campo de busca para filtrar modelos (por nome ou ID)
- Lista aparece ao clicar no campo, esconde apos selecionar
- Salva em `%APPDATA%\.rb-terminal\settings.json`

### gui/hosts_dialog.py

Tres dialogs:
- `HostDialog` - Adicionar/editar host
- `PasswordPromptDialog` - Pedir senha ao conectar
- `QuickConnectDialog` - Conexao rapida sem salvar

**Campos principais (sempre visiveis):**
- Nome, Host/IP, Porta, Usuario, Senha, Tipo Dispositivo

**Opcoes Avancadas (secao colapsavel):**
- Tipo Terminal (default: `xterm`, opcoes: `xterm-256color`, `vt100`)
- Toggle com botao "▶ Opcoes Avancadas" / "▼ Opcoes Avancadas"

**Campo removido:**
- "Desabilitar deteccao de terminal" - nao e mais necessario, a deteccao automatica de cores MikroTik funciona via `_respond_to_terminal_queries_async()` em [ssh_session.py](core/ssh_session.py)

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
      "disable_terminal_detection": false,
      "created_at": "2025-01-15T10:00:00"
    }
  ]
}
```

**Notas:**
- `terminal_type` default e `xterm` (mais compativel). Use `xterm-256color` para cores avancadas ou `vt100` para dispositivos muito antigos.
- `disable_terminal_detection` e deprecated, sempre `false` para novos hosts (mantido apenas para retrocompatibilidade).

## Fluxo do Usuario

1. Abre app -> ve lista de hosts salvos
2. Duplo clique no host -> conecta SSH:
   - Se tem credenciais salvas -> conecta automaticamente
   - Se nao tem -> terminal pede usuario/senha (estilo PuTTY)
3. Se conexao cair -> terminal mostra "Pressione R para reconectar"
4. Usa terminal normalmente OU abre chat IA (Ctrl+I)
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
- pyte

### Executar

**Modo normal (logs INFO):**
```bash
python main.py
```

**Modo debug (logs DEBUG detalhados):**
```bash
python main.py --debug
```

O modo debug exibe logs detalhados de todas as operações, incluindo:
- Chamadas HTTP para API OpenRouter
- Detalhes de conexões SSH
- Parsing de terminal queries
- Erros e stack traces completos

### Build Windows

```bash
pyinstaller --onefile --windowed main.py
```

## Debugging e Troubleshooting

### Modo Debug

Para diagnosticar problemas, rode a aplicacao com o parametro `--debug`:

```bash
python main.py --debug
```

Isso ativa logs DEBUG detalhados de:
- **Conexoes SSH**: handshake, auth, canais
- **Terminal queries**: respostas automaticas para MikroTik (DA1, DA2, cursor position)
- **API calls**: requisicoes e respostas da OpenRouter API
- **Agente IA**: execucao de comandos, tool calls, thinking
- **asyncio**: eventos de event loop (proactor, workers)

### Logs Importantes

**Conexao SSH bem-sucedida:**
```
core.ssh_session - INFO - Connecting to 192.168.1.1:22
core.ssh_session - INFO - SSH connection established (terminal: xterm)
core.ssh_session - INFO - Proactive terminal response enabled (for MikroTik colors)
```

**Deteccao automatica de cores MikroTik (DEBUG):**
```
core.ssh_session - DEBUG - CursorTracker: Query ESC[6n -> Response b'\x1b[53;1R'
core.ssh_session - DEBUG - Proactive response: DA1 -> VT220
```

**Erro de API OpenRouter:**
```
core.agent - ERROR - API request failed: 401 Unauthorized
```

### Problemas Comuns

**1. Cores nao aparecem em MikroTik**
- Verifique nos logs DEBUG se `Proactive terminal response enabled` aparece
- O sistema responde automaticamente a terminal queries (DA1, DA2)
- Nao e mais necessario usar `disable_terminal_detection` (deprecated)

**2. IA nao executa comandos**
- Rode com `--debug` e verifique logs de `core.agent`
- Verifique se API key esta configurada corretamente
- Confirme que o modelo suporta tool calling (ex: Claude, Gemini 2.0+)

**3. Desconexao inesperada SSH**
- Verifique logs: `ConnectionLost`, `BrokenPipeError`, `EOF`
- Pressione `R` para reconectar automaticamente

## Funcionalidades Pendentes (v2)

- [ ] SFTP file browser
- [ ] Multiplas sessoes em abas
- [ ] Historico de chat persistido
- [ ] Suporte a chaves SSH
- [ ] Lista de comandos perigosos configuravel
- [ ] Timeout de comandos configuravel

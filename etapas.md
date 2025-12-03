# Plano de Desenvolvimento - Terminal SSH com IA

## Filosofia
- Cada etapa deve **compilar** e ser **testável**
- Só avançar após validação da etapa anterior
- Estrutura pensada desde o início para evitar retrabalho
- Código modular para facilitar extensões futuras

---

## Stack Tecnologica
| Componente    | Tecnologia/Decisão                     |
|---------------|----------------------------------------|
| Linguagem     | Python 3.11+                           |
| GUI           | PySide6 + qasync                       |
| Agente IA     | PydanticAI (executando via OpenRouter) |
| LLM Provider  | OpenRouter (modelo padrão: google/gemini-2.5-flash) |
| SSH/SFTP      | asyncssh                               |
| Terminal Type | xterm como padrão, vt100 como fallback |
| Criptografia  | `cryptography` (Fernet)                |
| Persistencia  | Arquivos JSON locais + chave Fernet    |
| Build         | PyInstaller (.exe)                     |

### Justificativas principais
- asyncssh: API moderna assincrona com SSH e SFTP integrados.
- xterm/vt100: cobre Mikrotik, Cisco e Linux antigos; fallback automatico.
- cryptography/Fernet: criptografia simetrica segura e mantida.
- Persistencia local: simples para backup/edicao manual, sem dependencias externas.

## Escopo Geral e Princípios
1. **Gerenciador de Hosts:** CRUD completo, senhas criptografadas e login automático (duplo clique).
2. **Terminal SSH:** múltiplas sessões, histórico, PTY resize, suporte Mikrotik/Cisco/Linux e indicador de status.
3. **Gerenciador SFTP:** navegação, upload/download, CRUD de arquivos integrado à mesma sessão SSH.
4. **Chat IA agentico:** painel lateral que executa comandos via tools (`execute_command`, `read_file`, etc.).
5. **Execucao 100% local:** configuracoes em `~/.rb-terminal/` (ou `%APPDATA%\.rb-terminal`), sem DB externo.
6. **Controle e Seguranca:** botao "Parar IA", confirmacao para comandos destrutivos e timeouts configuraveis.
7. **Gerenciamento de Conexao:** detectar quedas, reconectar e apresentar mensagens claras ao usuario.

## Arquitetura Sugerida
```
rb-terminal/
├── main.py
├── core/
│   ├── agent.py
│   ├── ssh_session.py
│   ├── sftp_manager.py
│   ├── hosts.py
│   ├── crypto.py
│   ├── commands.py
│   └── history.py
├── gui/
│   ├── main_window.py
│   ├── terminal_widget.py
│   ├── chat_widget.py
│   ├── file_browser.py
│   └── hosts_dialog.py
└── config/
    └── settings.json
```

`core/history.py` deve persistir o histórico do chat/local por sessão para que a IA mantenha contexto mesmo após reiniciar o app.

---

## ETAPA 1: Fundação - Terminal SSH Básico
**Objetivo:** App que compila, abre janela e conecta via SSH  
**Status:** Concluída

### Arquivos a criar:
```
rb-terminal/
├── main.py
├── core/
│   └── ssh_session.py
├── gui/
│   ├── main_window.py
│   └── terminal_widget.py
├── requirements.txt
└── build.spec (PyInstaller)
```

### Funcionalidades:
- [x] Janela PySide6 básica com campos: Host, Porta, Usuário, Senha
- [x] Botão "Conectar"
- [x] Widget de terminal (área de texto para output + input)
- [x] Conexão SSH com asyncssh
- [x] Enviar comandos e exibir resposta em tempo real
- [x] Botão "Desconectar"

### Critérios de aceite:
1. `python main.py` abre a janela
2. Preencher dados de um host Linux/Mikrotik e conectar
3. Digitar comando (ex: `ls` ou `/system resource print`) e ver output
4. Desconectar sem crash
5. `pyinstaller build.spec` gera .exe funcional

### Dependências (requirements.txt):
```
PySide6>=6.6.0
asyncssh>=2.14.0
qasync>=0.27.0
```

### Notas técnicas:
- Usar `qasync` para integrar asyncio com Qt event loop.
- Terminal widget preparado para cores ANSI e ajuste de tamanho (xterm por padrão, vt100 como fallback).
- `ssh_session.py` deve manter interface limpa para IA e SFTP.
- Logging básico habilitado desde o início para depuração.

---

## ETAPA 2: Integração do Agente IA
**Objetivo:** Chat com IA que executa comandos no terminal  
**Status:** Concluída

### Arquivos a criar/modificar:
```
├── core/
│   ├── ssh_session.py      # expor métodos usados pela IA
│   ├── agent.py            # NOVO
│   └── history.py          # NOVO - persistência das conversas
├── gui/
│   ├── main_window.py      # adicionar painel de chat
│   └── chat_widget.py      # NOVO
└── config/
    └── settings.json       # API key OpenRouter
```

### Funcionalidades:
- [x] Configuração da API key OpenRouter (settings.json)
- [x] Widget de chat lateral (input + histórico persistido em `history.py`)
- [x] Agente PydanticAI com tool `execute_command`
- [x] IA envia comando → aparece no terminal → output volta pra IA
- [x] Loop agentico com múltiplos comandos em sequência
- [x] Mensagens da IA aparecem no chat com contexto do tipo de dispositivo

### Critérios de aceite:
1. Configurar API key no settings.json.
2. Conectar SSH em um Linux.
3. No chat: "Liste os arquivos do diretório atual".
4. IA executa `ls -la`, vê output, responde no chat.
5. No chat: "Qual o uso de memória?" → IA executa `free -h` e responde.
6. Comandos aparecem no terminal em tempo real.

### Dependências adicionais:
```
pydantic-ai>=0.0.20
httpx>=0.27.0
```

### Notas técnicas:
- Agent roda em task async separada e sinaliza status no UI.
- Output precisa ser encaminhado tanto para o terminal quanto para o agent loop.
- `device_type` do host é enviado para a IA (Linux, MikroTik, Cisco, etc.) para ajustar comandos sugeridos.
- Histórico de chat é persistido por sessão para manter contexto após fechar o app.
- Streaming de resposta da IA continua opcional.

### Configuração OpenRouter:
- **Modelo:** `google/gemini-2.5-flash`
- **API Key:** Configurar via Settings no app

### Exemplo de agente (PydanticAI)
```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel

class SSHSession(BaseModel):
    # wrapper da conexão asyncssh ativa (SSH + SFTP)
    ...

agent = Agent(
    "openrouter/anthropic/claude-3.5-sonnet",
    deps_type=SSHSession,
    system_prompt="Você é especialista em Mikrotik, Cisco e Linux."
)

@agent.tool
async def execute_command(ctx: RunContext[SSHSession], command: str) -> str:
    return await ctx.deps.execute(command)
```

### Exemplo de uso (curl):
```bash
curl -s "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "Quanto é 2 + 2?"}
    ],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "resposta",
        "strict": true,
        "schema": {
          "type": "object",
          "properties": {
            "resultado": {"type": "string"}
          },
          "required": ["resultado"]
        }
      }
    }
  }'
```

### Resposta esperada:
```json
{
  "provider": "Google",
  "model": "google/gemini-2.5-flash",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "{\"resultado\": \"4\"}"
    }
  }]
}
```

---

## ETAPA 3: Gerenciador de Hosts
**Objetivo:** Salvar hosts e conectar com duplo clique  
**Status:** Concluída

### Arquivos a criar/modificar:
```
├── core/
│   ├── hosts.py            # NOVO - CRUD hosts
│   └── crypto.py           # NOVO - criptografia senhas
├── gui/
│   ├── main_window.py      # adicionar lista de hosts
│   └── hosts_dialog.py     # NOVO - dialog adicionar/editar
└── config/
    └── hosts.json          # dados dos hosts
```

### Funcionalidades:
- [x] Lista de hosts na lateral esquerda
- [x] Botão "Adicionar Host" → dialog com campos
- [x] Editar host (clique direito → Editar)
- [x] Excluir host (clique direito → Excluir)
- [x] Duplo clique → conecta automaticamente com credenciais salvas
- [x] Senhas criptografadas com Fernet, chave salva separada
- [x] Campo `terminal_type` e `device_type` por host (xterm/vt100/custom)
- [x] Opção de não salvar senha (prompt no momento da conexão)

### Critérios de aceite:
1. Adicionar host "Mikrotik" com IP, porta, usuário, senha
2. Host aparece na lista
3. Fechar e reabrir app → host ainda está lá
4. Duplo clique → conecta sem pedir senha
5. Senha no hosts.json está criptografada (não legível)
6. Editar host funciona
7. Excluir host funciona

### Notas técnicas:
- Chave Fernet gerada no primeiro uso e salva em arquivo separado
- `hosts.json` fica em `~/.rb-terminal/` (ou `%APPDATA%\.rb-terminal`)
- `disable_terminal_detection` disponível para hosts MikroTik (adiciona sufixo `+ct`)
- Estrutura de dados deve guardar `created_at` para auditoria
- Dialogs compartilham validações com `core/hosts.py`

---

## ETAPA 4: Terminal Avançado
**Objetivo:** Múltiplas abas, cores, histórico
**Status:** Concluída

### Arquivos a modificar:
```
├── gui/
│   ├── main_window.py      # sistema de abas
│   ├── tab_session.py      # NOVO - dataclass para estado da aba
│   └── terminal_widget.py  # melhorias
```

### Funcionalidades:
- [x] Abas para múltiplas sessões SSH
- [x] Nova aba: Ctrl+T ou botão "+"
- [x] Fechar aba: botão X na aba (Ctrl+W)
- [x] Navegação entre abas: Ctrl+Left / Ctrl+Right
- [x] Histórico de comandos por sessão (setas ↑↓) (funciona nativamente pelos hosts)
- [x] Suporte a cores ANSI (output colorido compatível com Mikrotik/Cisco/Linux)
- [x] Redimensionamento de terminal (PTY resize)
- [x] Indicador de status na aba (conectado/desconectado/conectando)
- [x] Banner de modo desconectado com instrução "Pressione R para reconectar"

### Critérios de aceite:
1. Conectar em 2 hosts diferentes em abas separadas
2. Alternar entre abas (ctrl + → e ctrl + ← )
3. Comando com cores (ex: `ls --color`) mostra colorido
4. Seta pra cima recupera último comando (já funciona)
5. Redimensionar janela → terminal se ajusta
6. Fechar aba desconecta a sessão

### Notas técnicas:
- QTabWidget para abas com ícones de status por sessão.
- Parser ANSI/pyte já integrado; manter respostas VT220 aos queries do MikroTik (DA1/DA2) e fallback `+ct`.
- Histórico de comandos mantido em lista por sessão e persistido opcionalmente em `core/history.py`.
- Ajustar PTY via `asyncssh.SSHClientConnection.create_session` (métodos de resize conectados ao evento de resize da janela Qt).
- Quando desconectar manualmente, limpar `_last_config` para impedir reconexão automática indesejada.

---

## ETAPA 5: Gerenciador de Arquivos (SFTP)
**Objetivo:** Navegar pastas, upload/download

### Arquivos a criar/modificar:
```
├── core/
│   ├── sftp_manager.py     # NOVO
│   └── agent.py            # adicionar tools SFTP
├── gui/
│   ├── main_window.py      # botão SFTP
│   └── file_browser.py     # NOVO
```

### Funcionalidades:
- [ ] Botão "Arquivos" abre file browser
- [ ] Navegar pastas do host remoto
- [ ] Download: selecionar arquivo → salvar local
- [ ] Upload: arrastar arquivo ou botão
- [ ] Criar pasta
- [ ] Renomear arquivo/pasta
- [ ] Excluir arquivo/pasta
- [ ] Tools da IA: read_file, write_file, list_directory, upload_file, download_file

### Critérios de aceite:
1. Abrir file browser em sessão conectada
2. Navegar até /etc/, ver arquivos
3. Download de arquivo funciona
4. Upload de arquivo funciona
5. IA: "Leia o conteúdo do /etc/hostname" → funciona
6. IA: "Crie um arquivo teste.txt com conteúdo 'hello'" → funciona

### Notas técnicas:
- SFTP usa mesma conexão SSH (asyncssh suporta)
- File browser pode ser dock widget ou dialog flutuante, reaproveitando sessão aberta
- IA deve reutilizar as mesmas ferramentas (`read_file`, `write_file`, `list_directory`, `upload_file`, `download_file`) para cumprir o loop agentico descrito no escopo geral
- Upload deve oferecer opção de sobrescrever/renomear em caso de conflito
- Operações críticas (delete/rename) devem pedir confirmação e herdar política da Etapa 6

---

## ETAPA 6: Segurança e Controle
**Objetivo:** Proteções e robustez

### Arquivos a criar/modificar:
```
├── core/
│   ├── commands.py         # NOVO - validação
│   ├── agent.py            # timeout, cancelamento
│   └── ssh_session.py      # reconexão
├── gui/
│   └── chat_widget.py      # botão parar
```

### Funcionalidades:
- [ ] Botão "Parar IA" cancela execução
- [ ] Confirmação para comandos perigosos (rm, format, reset, etc.)
- [ ] Lista de comandos perigosos configurável
- [ ] Timeout de 30s para comandos (pede confirmação para continuar)
- [ ] Detecção de conexão perdida
- [ ] Botão/opção reconectar
- [ ] Mensagens de erro amigáveis

### Critérios de aceite:
1. IA executando → clicar "Parar" → para imediatamente
2. IA tentar rodar `rm -rf /` → popup de confirmação
3. Comando demorando > 30s → pergunta se quer continuar
4. Desconectar cabo de rede → app detecta e mostra status
5. Botão reconectar funciona

### Notas técnicas:
- Cancelamento via asyncio.Task.cancel()
- Lista de comandos perigosos em JSON configurável (`config/commands.json`)
- Heartbeat ou try/except para detectar desconexão; atualizar indicador visual imediatamente
- Timeout padrão 30s, com opção de estender no popup e logar decisão no histórico
- Botão "Parar IA" precisa cancelar tools em andamento e limpar estado do agente

---

## ETAPA 7: Polimento e Build Final
**Objetivo:** App pronto para uso

### Tarefas:
- [ ] Revisar UI/UX
- [ ] Ícone do app
- [ ] Splash screen (opcional)
- [ ] Tema dark consistente
- [ ] Testar em Windows 10/11
- [ ] Build final PyInstaller
- [ ] Testar .exe em máquina limpa
- [ ] Documentação básica (README)

### Critérios de aceite:
1. App abre sem erros em Windows limpo
2. Todas funcionalidades das etapas anteriores funcionando
3. UI consistente e agradável
4. Nenhum crash durante uso normal
5. .exe único (one-file) ou pasta com dependências

---

## Configurações Iniciais
- Arquivos moram em `~/.rb-terminal/` ou `%APPDATA%\.rb-terminal`.
- `settings.json` guarda API key, modelo padrão e tema.
- `hosts.json` mantém lista de hosts com campos `terminal_type`, `device_type`, `disable_terminal_detection` e `created_at`.

```json
// ~/.rb-terminal/settings.json
{
  "openrouter_api_key": "sk-or-...",
  "default_model": "anthropic/claude-3.5-sonnet",
  "theme": "dark"
}
```

```json
// ~/.rb-terminal/hosts.json
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

---

## Fluxo do Usuário
1. Abrir o app e visualizar a lista de hosts salvos.
2. Duplo clique no host desejado:
   - Se possuir credenciais salvas, conecta automaticamente.
   - Caso contrário, o terminal solicita usuário/senha (keyboard-interactive).
3. Usar o terminal normalmente ou abrir o chat IA (atalho `Ctrl+I`).
4. Opcional: abrir o navegador de arquivos SFTP para upload/download.
5. Durante o chat, o usuário vê em tempo real os comandos executados e pode interromper com "Parar IA".
6. Em caso de queda, o terminal mostra modo desconectado e permite reconectar com a tecla `R`.

---

## Entregáveis
- Código fonte Python completo.
- Executável Windows (.exe) gerado via PyInstaller.
- Documentação básica de uso (README + CLAUDE/ETAPAS atualizados).

---

## Fora do Escopo (v1)
- Suporte a chaves SSH (só usuário/senha por enquanto).
- Múltiplos provedores de IA simultâneos.
- Versões Mac/Linux (foco inicial no .exe Windows).

---

## Resumo Visual

```
ETAPA 1 ──► ETAPA 2 ──► ETAPA 3 ──► ETAPA 4 ──► ETAPA 5 ──► ETAPA 6 ──► ETAPA 7
   │           │           │           │           │           │           │
   ▼           ▼           ▼           ▼           ▼           ▼           ▼
SSH básico   + IA      + Hosts     + Abas      + SFTP    + Segurança  + Polish
compilar    funciona   salvos     cores       files     controles    .exe final
testar      testar     testar     testar      testar    testar       testar
```

---

## Ordem de Dependências

| Etapa | Depende de | Pode ser feito em paralelo com |
|-------|------------|--------------------------------|
| 1     | -          | -                              |
| 2     | 1          | -                              |
| 3     | 1          | 2 (parcialmente)               |
| 4     | 1          | 2, 3                           |
| 5     | 1, 2       | 3, 4                           |
| 6     | 2          | 3, 4, 5                        |
| 7     | Todas      | -                              |

---

## Compilação (Build)

### Requisitos
- Docker instalado e rodando
- Conexão com internet (para baixar imagem Docker)

### Como compilar para Windows (.exe)

```bash
# Dar permissão de execução (apenas primeira vez)
chmod +x build.sh

# Compilar
./build.sh
```

O executável será gerado em: `dist/RB-Terminal.exe`

### Arquivos de build
| Arquivo     | Descrição                              |
|-------------|----------------------------------------|
| build.sh    | Script de compilação (Linux → Windows) |
| build.bat   | Script de compilação (Windows nativo)  |
| build.spec  | Configuração do PyInstaller            |

### Compilação manual (alternativa)

```bash
# Via Docker (Linux gerando .exe Windows)
docker run --rm -v "$(pwd):/src" batonogov/pyinstaller-windows:latest \
    "pip install PySide6 asyncssh qasync && pyinstaller --onefile --noconsole --name RB-Terminal main.py"
```

```cmd
# No Windows (nativo)
pip install -r requirements.txt pyinstaller
pyinstaller build.spec
```

---

## Notas para o Programador

1. **Estrutura de pastas:** Criar desde a Etapa 1 mesmo que vazia
2. **Imports:** Usar imports relativos dentro do projeto
3. **Async:** Todo código SSH/IA deve ser async
4. **Configuração:** Usar pathlib para caminhos, funcionar em Windows
5. **Logs:** Adicionar logging básico desde o início (facilita debug)
6. **Testes manuais:** Cada etapa deve ser testada com dispositivo real (Linux ou Mikrotik)

# Plano de Desenvolvimento - Terminal SSH com IA

## Filosofia
- Cada etapa deve **compilar** e ser **testável**
- Só avançar após validação da etapa anterior
- Estrutura pensada desde o início para evitar retrabalho
- Código modular para facilitar extensões futuras

---

## ETAPA 1: Fundação - Terminal SSH Básico
**Objetivo:** App que compila, abre janela e conecta via SSH

### Arquivos a criar:
```
ssh-ai-terminal/
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
- [ ] Janela PySide6 básica com campos: Host, Porta, Usuário, Senha
- [ ] Botão "Conectar"
- [ ] Widget de terminal (área de texto para output + input)
- [ ] Conexão SSH com asyncssh
- [ ] Enviar comandos e exibir resposta
- [ ] Botão "Desconectar"

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
- Usar `qasync` para integrar asyncio com Qt event loop
- Terminal widget já deve ser pensado para receber cores ANSI depois (usar QTextEdit ou similar)
- ssh_session.py deve ter interface limpa que será reutilizada pela IA

---

## ETAPA 2: Integração do Agente IA
**Objetivo:** Chat com IA que executa comandos no terminal

### Arquivos a criar/modificar:
```
├── core/
│   ├── ssh_session.py      # adicionar método para IA usar
│   └── agent.py            # NOVO
├── gui/
│   ├── main_window.py      # adicionar painel de chat
│   └── chat_widget.py      # NOVO
└── config/
    └── settings.json       # API key OpenRouter
```

### Funcionalidades:
- [ ] Configuração da API key OpenRouter (settings.json)
- [ ] Widget de chat lateral (input + histórico de mensagens)
- [ ] Agente PydanticAI com tool `execute_command`
- [ ] IA envia comando → aparece no terminal → output volta pra IA
- [ ] IA pode fazer múltiplos comandos em sequência
- [ ] Mensagens da IA aparecem no chat

### Critérios de aceite:
1. Configurar API key no settings.json
2. Conectar SSH em um Linux
3. No chat: "Liste os arquivos do diretório atual"
4. IA executa `ls -la`, vê output, responde no chat
5. No chat: "Qual o uso de memória?" → IA executa `free -h` e responde
6. Comandos aparecem no terminal em tempo real

### Dependências adicionais:
```
pydantic-ai>=0.0.20
httpx>=0.27.0
```

### Notas técnicas:
- Agent roda em task async separada
- Output do comando deve ir pro terminal E voltar pra IA
- Streaming de resposta da IA opcional nesta etapa

### Configuração OpenRouter:
- **Modelo:** `google/gemini-2.5-flash`
- **API Key:** `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`

### Exemplo de uso (curl):
```bash
curl -s "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer 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" \
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
- [ ] Lista de hosts na lateral esquerda
- [ ] Botão "Adicionar Host" → dialog com campos
- [ ] Editar host (clique direito → Editar)
- [ ] Excluir host (clique direito → Excluir)
- [ ] Duplo clique → conecta automaticamente
- [ ] Senhas criptografadas com Fernet
- [ ] Campo terminal_type por host (xterm/vt100)

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
- hosts.json fica em ~/.ssh-ai-terminal/

---

## ETAPA 4: Terminal Avançado
**Objetivo:** Múltiplas abas, cores, histórico

### Arquivos a modificar:
```
├── gui/
│   ├── main_window.py      # sistema de abas
│   └── terminal_widget.py  # melhorias
```

### Funcionalidades:
- [ ] Abas para múltiplas sessões SSH
- [ ] Nova aba: Ctrl+T ou botão "+"
- [ ] Fechar aba: botão X na aba
- [ ] Histórico de comandos (setas ↑↓)
- [ ] Suporte a cores ANSI (output colorido)
- [ ] Redimensionamento de terminal (PTY resize)
- [ ] Indicador de status na aba (conectado/desconectado)

### Critérios de aceite:
1. Conectar em 2 hosts diferentes em abas separadas
2. Alternar entre abas
3. Comando com cores (ex: `ls --color`) mostra colorido
4. Seta pra cima recupera último comando
5. Redimensionar janela → terminal se ajusta
6. Fechar aba desconecta a sessão

### Notas técnicas:
- QTabWidget para abas
- ANSI parser para cores (lib `ansi2html` ou implementar básico)
- Histórico de comandos: lista por sessão

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
- File browser pode ser dock widget ou dialog

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
- Lista de comandos perigosos em JSON configurável
- Heartbeat ou try/except para detectar desconexão

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

O executável será gerado em: `dist/SSH-AI-Terminal.exe`

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
    "pip install PySide6 asyncssh qasync && pyinstaller --onefile --noconsole --name SSH-AI-Terminal main.py"
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

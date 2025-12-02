#!/bin/bash
# =============================================================================
# SSH AI Terminal - Build Script
# Compila o projeto para Windows (.exe) usando Docker
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="SSH-AI-Terminal"
DOCKER_IMAGE="batonogov/pyinstaller-windows:latest"

echo "=== SSH AI Terminal - Build ==="
echo ""

# Verificar se Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "ERRO: Docker não está instalado."
    echo "Instale Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Verificar se Docker está rodando
if ! docker info &> /dev/null; then
    echo "ERRO: Docker não está rodando."
    echo "Inicie o serviço Docker e tente novamente."
    exit 1
fi

echo "[1/3] Baixando imagem Docker (se necessário)..."
docker pull "$DOCKER_IMAGE" 2>&1 | tail -3

echo ""
echo "[2/3] Compilando para Windows..."
docker run --rm \
    -v "$SCRIPT_DIR:/src" \
    "$DOCKER_IMAGE" \
    "pip install PySide6 asyncssh qasync httpx pywin32 && pyinstaller --onefile --noconsole --name $PROJECT_NAME --add-data 'config/settings.json:config' main.py"

echo ""
echo "[3/3] Ajustando permissões..."
if [ -f "$SCRIPT_DIR/dist/$PROJECT_NAME.exe" ]; then
    # Corrigir permissões se rodando como usuário normal
    if [ "$(id -u)" != "0" ]; then
        sudo chown "$(id -u):$(id -g)" "$SCRIPT_DIR/dist/$PROJECT_NAME.exe" 2>/dev/null || true
    fi

    # Limpar arquivos de build
    rm -rf "$SCRIPT_DIR/build" 2>/dev/null || true

    echo ""
    echo "=== BUILD CONCLUÍDO ==="
    echo "Executável: $SCRIPT_DIR/dist/$PROJECT_NAME.exe"
    echo "Tamanho: $(du -h "$SCRIPT_DIR/dist/$PROJECT_NAME.exe" | cut -f1)"
    echo ""
else
    echo "ERRO: Falha na compilação. Verifique os logs acima."
    exit 1
fi

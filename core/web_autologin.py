# web_autologin.py - Auto-login para MikroTik, Zabbix e Proxmox
"""
Módulo para auto-login em interfaces web de MikroTik, Zabbix e Proxmox.
Usa Selenium para abrir navegador com sessão autenticada.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import glob
import logging
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


def detect_default_browser() -> str:
    """Detecta o navegador padrão do Windows."""
    if sys.platform != "win32":
        return "chrome"  # Default para outros sistemas

    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]

            if "Edge" in prog_id or "MSEdge" in prog_id:
                return "edge"
            elif "Chrome" in prog_id:
                return "chrome"
            elif "Firefox" in prog_id:
                return "firefox"
            elif "Opera" in prog_id:
                return "opera"
            else:
                logger.info(f"Navegador '{prog_id}' não suportado, usando Edge")
                return "edge"
    except Exception as e:
        logger.warning(f"Erro ao detectar navegador padrão: {e}")
        return "edge"


def _copy_chromium_profile(original_path: str, temp_path: str, browser_name: str, use_default: bool = True):
    """Copia perfil de navegadores baseados em Chromium (Edge/Chrome/Opera)."""
    if os.path.exists(temp_path):
        return  # Já existe

    logger.info(f"Copiando perfil do {browser_name}...")
    os.makedirs(temp_path, exist_ok=True)

    def ignore_files(directory, files):
        ignore = set()
        folders_to_ignore = {"Cache", "Code Cache", "GPUCache", "Service Worker",
                           "Network", "Safe Browsing Network", "blob_storage",
                           "Session Storage", "Sessions", "IndexedDB",
                           "ShaderCache", "TransportSecurity"}
        for f in files:
            if f in folders_to_ignore:
                ignore.add(f)
            elif f.endswith((".log", ".tmp", "-journal")):
                ignore.add(f)
        return ignore

    try:
        if use_default:
            source = os.path.join(original_path, "Default")
            dest = os.path.join(temp_path, "Default")
            if os.path.exists(source):
                shutil.copytree(source, dest, ignore=ignore_files, dirs_exist_ok=True)
        else:
            shutil.copytree(original_path, temp_path, ignore=ignore_files, dirs_exist_ok=True)

        local_state = os.path.join(original_path, "Local State")
        if os.path.exists(local_state):
            shutil.copy2(local_state, temp_path)
    except Exception as e:
        logger.warning(f"Erro ao copiar perfil: {e}")


def _copy_firefox_profile(temp_path: str) -> Optional[str]:
    """Copia perfil do Firefox."""
    if os.path.exists(temp_path):
        return temp_path

    logger.info("Copiando perfil do Firefox...")

    firefox_profiles = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
    profiles = glob.glob(os.path.join(firefox_profiles, "*.default-release"))
    if not profiles:
        profiles = glob.glob(os.path.join(firefox_profiles, "*.default"))
    if not profiles:
        logger.warning("Nenhum perfil Firefox encontrado")
        return None

    original_path = profiles[0]
    logger.info(f"Usando perfil: {os.path.basename(original_path)}")

    def ignore_files(directory, files):
        ignore = set()
        folders_to_ignore = {"cache2", "startupCache", "storage", "shader-cache"}
        for f in files:
            if f in folders_to_ignore:
                ignore.add(f)
            elif f.endswith((".log", ".tmp", "-journal", ".sqlite-wal", ".sqlite-shm")):
                ignore.add(f)
            elif f in ["lock", "parent.lock", ".parentlock"]:
                ignore.add(f)
        return ignore

    try:
        shutil.copytree(original_path, temp_path, ignore=ignore_files, dirs_exist_ok=True)
        return temp_path
    except Exception as e:
        logger.warning(f"Erro ao copiar perfil Firefox: {e}")
        return None


def _create_browser_driver(browser: str):
    """Cria driver do navegador com perfil copiado."""
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions

    if browser == "edge":
        options = EdgeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)  # Mantém navegador aberto

        user_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data")
        temp_profile = os.path.join(tempfile.gettempdir(), "EdgeSeleniumProfile")
        _copy_chromium_profile(user_data, temp_profile, "Edge")

        options.add_argument(f"--user-data-dir={temp_profile}")
        options.add_argument("--profile-directory=Default")
        return webdriver.Edge(options=options)

    elif browser == "chrome":
        options = ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)  # Mantém navegador aberto

        user_data = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
        temp_profile = os.path.join(tempfile.gettempdir(), "ChromeSeleniumProfile")
        _copy_chromium_profile(user_data, temp_profile, "Chrome")

        options.add_argument(f"--user-data-dir={temp_profile}")
        options.add_argument("--profile-directory=Default")
        return webdriver.Chrome(options=options)

    elif browser == "firefox":
        options = FirefoxOptions()
        temp_profile = os.path.join(tempfile.gettempdir(), "FirefoxSeleniumProfile")
        profile = _copy_firefox_profile(temp_profile)

        if profile:
            options.add_argument("-profile")
            options.add_argument(temp_profile)

        driver = webdriver.Firefox(options=options)
        driver.maximize_window()
        return driver

    elif browser == "opera":
        options = ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)  # Mantém navegador aberto

        # Encontra executável do Opera
        opera_paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Opera GX", "opera.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Opera", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Opera", "opera.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Opera", "opera.exe"),
        ]
        opera_exe = None
        for path in opera_paths:
            if os.path.exists(path):
                opera_exe = path
                break

        if opera_exe:
            options.binary_location = opera_exe
            is_gx = "Opera GX" in opera_exe
        else:
            is_gx = False

        # Perfil
        if is_gx:
            original = os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera GX Stable")
            temp_profile = os.path.join(tempfile.gettempdir(), "OperaGXSeleniumProfile")
        else:
            original = os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera Stable")
            temp_profile = os.path.join(tempfile.gettempdir(), "OperaSeleniumProfile")

        if os.path.exists(original):
            _copy_chromium_profile(original, temp_profile, "Opera GX" if is_gx else "Opera", use_default=False)
            options.add_argument(f"--user-data-dir={temp_profile}")

        # Usa webdriver-manager para baixar driver compatível
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            chromium_version = "140" if is_gx else "131"
            service = Service(ChromeDriverManager(driver_version=chromium_version).install())
            return webdriver.Chrome(service=service, options=options)
        except ImportError:
            logger.warning("webdriver-manager não instalado, usando driver padrão")
            return webdriver.Chrome(options=options)

    else:
        raise ValueError(f"Navegador '{browser}' não suportado")


def _auth_proxmox_api(url: str, username: str, password: str) -> list:
    """Autentica no Proxmox via API e retorna cookies."""
    logger.info("Autenticando via API Proxmox...")

    # Adiciona @pam se não tiver realm especificado
    if "@" not in username:
        username = f"{username}@pam"
        logger.info(f"Realm não especificado, usando: {username}")

    response = requests.post(
        f"{url}/api2/json/access/ticket",
        data={
            "username": username,
            "password": password
        },
        verify=False,
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(f"Falha na autenticação Proxmox: {response.status_code}")

    data = response.json()["data"]
    ticket = data["ticket"]
    logger.info(f"Ticket Proxmox obtido: {ticket[:40]}...")

    return [
        {"name": "PVEAuthCookie", "value": ticket, "path": "/", "secure": True}
    ]


def _auth_zabbix_api(url: str, username: str, password: str) -> list:
    """Autentica no Zabbix via API JSON-RPC e retorna cookies."""
    logger.info("Autenticando via API Zabbix...")

    # Login web para obter cookies
    session = requests.Session()
    login_response = session.post(
        f"{url}/index.php",
        data={
            "name": username,
            "password": password,
            "enter": "Sign in"
        },
        verify=False,
        timeout=30
    )

    cookies = []
    for cookie in session.cookies:
        cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "path": cookie.path or "/",
            "secure": cookie.secure
        })

    logger.info(f"Cookies Zabbix obtidos: {len(cookies)}")
    return cookies


def autologin_proxmox(url: str, username: str, password: str):
    """
    Abre navegador com sessão autenticada no Proxmox.

    Args:
        url: URL do Proxmox (ex: https://10.8.200.254:8006)
        username: Usuário (ex: root@pam)
        password: Senha

    Returns:
        WebDriver com sessão autenticada
    """
    # Obtém cookies via API
    cookies = _auth_proxmox_api(url, username, password)

    # Abre navegador
    browser = detect_default_browser()
    logger.info(f"Abrindo navegador ({browser})...")
    driver = _create_browser_driver(browser)

    # Acessa URL primeiro (necessário para setar cookies)
    driver.get(url)
    time.sleep(1)

    # Injeta cookies
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
            logger.info(f"Cookie '{cookie['name']}' injetado")
        except Exception as e:
            logger.warning(f"Aviso ao injetar cookie: {e}")

    # Recarrega com autenticação
    driver.get(url)
    logger.info("Sessão Proxmox autenticada!")

    return driver


def autologin_zabbix(url: str, username: str, password: str):
    """
    Abre navegador com sessão autenticada no Zabbix.

    Args:
        url: URL do Zabbix (ex: http://10.8.200.10)
        username: Usuário
        password: Senha

    Returns:
        WebDriver com sessão autenticada
    """
    # Obtém cookies via login web
    cookies = _auth_zabbix_api(url, username, password)

    # Abre navegador
    browser = detect_default_browser()
    logger.info(f"Abrindo navegador ({browser})...")
    driver = _create_browser_driver(browser)

    # Acessa URL primeiro
    driver.get(url)
    time.sleep(1)

    # Injeta cookies
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
            logger.info(f"Cookie '{cookie['name']}' injetado")
        except Exception as e:
            logger.warning(f"Aviso ao injetar cookie: {e}")

    # Recarrega com autenticação
    driver.get(url)
    logger.info("Sessão Zabbix autenticada!")

    return driver


def autologin_mikrotik(url: str, username: str, password: str):
    """
    Abre navegador com sessão autenticada no MikroTik WebFig.

    Args:
        url: URL do MikroTik (ex: http://10.10.10.1:64780)
        username: Usuário
        password: Senha

    Returns:
        WebDriver com sessão autenticada
    """
    # Verifica credenciais via API REST (opcional)
    logger.info("Verificando credenciais MikroTik...")
    try:
        session = requests.Session()
        session.auth = (username, password)
        response = session.get(
            f"{url}/rest/system/identity",
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            identity = response.json()
            logger.info(f"Conectado ao router: {identity.get('name', 'MikroTik')}")
        elif response.status_code == 401:
            raise Exception("Credenciais MikroTik inválidas")
    except requests.exceptions.Timeout:
        logger.warning("Timeout na API REST MikroTik, continuando...")
    except requests.exceptions.ConnectionError:
        logger.warning("API REST MikroTik não disponível, continuando...")

    # Abre navegador
    browser = detect_default_browser()
    logger.info(f"Abrindo navegador ({browser})...")
    driver = _create_browser_driver(browser)

    # Acessa WebFig
    driver.get(url)
    time.sleep(2)

    # Preenche credenciais via JavaScript
    user_escaped = json.dumps(username)
    pass_escaped = json.dumps(password)

    logger.info("Preenchendo credenciais via JavaScript...")
    driver.execute_script(f'''
        var nameField = document.getElementById('name');
        var passField = document.getElementById('password');
        if (nameField) nameField.value = {user_escaped};
        if (passField) passField.value = {pass_escaped};
    ''')

    # Submete login
    logger.info("Submetendo login...")
    driver.execute_script('''
        var submitBtn = document.querySelector('input[type="submit"]');
        if (submitBtn) submitBtn.click();
    ''')

    time.sleep(3)
    logger.info("Sessão MikroTik autenticada!")

    return driver

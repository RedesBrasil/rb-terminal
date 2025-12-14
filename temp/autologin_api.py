# login_api.py - Metodo API + Cookie Injection (mais leve)
import requests
import urllib3
import json
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
import time
import sys
import os
import shutil
import tempfile
import glob

def detectar_navegador_padrao():
    """Detecta o navegador padrao do Windows"""
    try:
        import winreg
        # Chave do registro que armazena o navegador padrao
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
                print(f"Navegador '{prog_id}' nao suportado, usando Edge")
                return "edge"
    except Exception as e:
        print(f"Erro ao detectar navegador padrao: {e}")
        return "edge"

# Navegador padrao (detectado automaticamente)
NAVEGADOR = detectar_navegador_padrao()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuracao dos servicos
SERVICOS = {
    "zabbix": {
        "url": "http://10.8.200.10",
        "username": "user123",
        "password": "senha123"
    },
    "proxmox": {
        "url": "https://10.8.200.254:8006",
        "username": "user123@pam",
        "password": "senha123"
    },
    "mikrotik": {
        "url": "http://10.10.10.1:64780",
        "username": "user123",
        "password": "senha123"
    }
}


def auth_proxmox(config):
    """Autentica no Proxmox via API e retorna cookies"""
    print("Autenticando via API Proxmox...")

    response = requests.post(
        f"{config['url']}/api2/json/access/ticket",
        data={
            "username": config["username"],
            "password": config["password"]
        },
        verify=False
    )

    if response.status_code != 200:
        raise Exception(f"Falha na autenticacao: {response.status_code}")

    data = response.json()["data"]
    ticket = data["ticket"]

    print(f"Ticket obtido: {ticket[:40]}...")

    return [
        {"name": "PVEAuthCookie", "value": ticket, "path": "/", "secure": True}
    ]


def auth_zabbix(config):
    """Autentica no Zabbix via API JSON-RPC e retorna cookies"""
    print("Autenticando via API Zabbix...")

    # Zabbix API JSON-RPC
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {
            "username": config["username"],
            "password": config["password"]
        },
        "id": 1
    }

    response = requests.post(
        f"{config['url']}/api_jsonrpc.php",
        json=payload,
        headers={"Content-Type": "application/json-rpc"},
        verify=False
    )

    if response.status_code != 200:
        raise Exception(f"Falha na autenticacao: {response.status_code}")

    result = response.json()

    if "error" in result:
        raise Exception(f"Erro API: {result['error']}")

    token = result["result"]
    print(f"Token obtido: {token[:40]}...")

    # Zabbix usa cookie de sessao via login web
    # Fazemos login web para obter o cookie
    session = requests.Session()
    login_response = session.post(
        f"{config['url']}/index.php",
        data={
            "name": config["username"],
            "password": config["password"],
            "enter": "Sign in"
        },
        verify=False
    )

    cookies = []
    for cookie in session.cookies:
        cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "path": cookie.path or "/",
            "secure": cookie.secure
        })

    print(f"Cookies obtidos: {len(cookies)}")
    return cookies


def auth_mikrotik(config):
    """Autentica no Mikrotik - verifica credenciais via API REST"""
    print("Verificando credenciais Mikrotik...")

    session = requests.Session()
    session.auth = (config["username"], config["password"])

    # Verifica credenciais via API REST
    try:
        response = session.get(
            f"{config['url']}/rest/system/identity",
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            identity = response.json()
            print(f"Conectado ao router: {identity.get('name', 'Mikrotik')}")
        elif response.status_code == 401:
            raise Exception("Credenciais invalidas")
        else:
            print(f"API retornou status: {response.status_code}")
    except requests.exceptions.Timeout:
        print("Timeout na API REST, continuando...")
    except requests.exceptions.ConnectionError:
        print("API REST nao disponivel, continuando...")

    # WebFig suporta auto-login via window.name
    # Formato: "autologin=usuario|senha"
    return {"webfig_autologin": True}


def copiar_perfil_chromium(perfil_original, perfil_temp, nome_navegador, usa_default=True):
    """Copia perfil de navegadores baseados em Chromium (Edge/Chrome/Opera)"""
    if not os.path.exists(perfil_temp):
        print(f"Copiando perfil do {nome_navegador} (primeira execucao)...")
        os.makedirs(perfil_temp, exist_ok=True)

        def ignorar_arquivos(diretorio, arquivos):
            ignorar = set()
            pastas_ignorar = {"Cache", "Code Cache", "GPUCache", "Service Worker",
                             "Network", "Safe Browsing Network", "blob_storage",
                             "Session Storage", "Sessions", "IndexedDB",
                             "ShaderCache", "TransportSecurity"}
            for arquivo in arquivos:
                if arquivo in pastas_ignorar:
                    ignorar.add(arquivo)
                elif arquivo.endswith((".log", ".tmp", "-journal")):
                    ignorar.add(arquivo)
            return ignorar

        if usa_default:
            # Edge/Chrome usam subpasta Default
            shutil.copytree(
                os.path.join(perfil_original, "Default"),
                os.path.join(perfil_temp, "Default"),
                ignore=ignorar_arquivos,
                dirs_exist_ok=True
            )
        else:
            # Opera armazena direto na pasta raiz
            shutil.copytree(
                perfil_original,
                perfil_temp,
                ignore=ignorar_arquivos,
                dirs_exist_ok=True
            )

        local_state = os.path.join(perfil_original, "Local State")
        if os.path.exists(local_state):
            shutil.copy2(local_state, perfil_temp)


def copiar_perfil_firefox(perfil_temp):
    """Copia perfil do Firefox"""
    if not os.path.exists(perfil_temp):
        print("Copiando perfil do Firefox (primeira execucao)...")

        # Encontra o perfil padrao do Firefox
        firefox_profiles = os.path.join(os.environ["APPDATA"], "Mozilla", "Firefox", "Profiles")
        perfis = glob.glob(os.path.join(firefox_profiles, "*.default-release"))
        if not perfis:
            perfis = glob.glob(os.path.join(firefox_profiles, "*.default"))
        if not perfis:
            print("  Nenhum perfil Firefox encontrado, usando perfil limpo")
            return None

        perfil_original = perfis[0]
        print(f"  Usando perfil: {os.path.basename(perfil_original)}")

        def ignorar_arquivos(diretorio, arquivos):
            ignorar = set()
            pastas_ignorar = {"cache2", "startupCache", "storage", "shader-cache"}
            for arquivo in arquivos:
                if arquivo in pastas_ignorar:
                    ignorar.add(arquivo)
                elif arquivo.endswith((".log", ".tmp", "-journal", ".sqlite-wal", ".sqlite-shm")):
                    ignorar.add(arquivo)
                elif arquivo in ["lock", "parent.lock", ".parentlock"]:
                    ignorar.add(arquivo)
            return ignorar

        shutil.copytree(
            perfil_original,
            perfil_temp,
            ignore=ignorar_arquivos,
            dirs_exist_ok=True
        )

    return perfil_temp


def open_browser(url, cookies, config):
    """Abre navegador com cookies injetados"""
    global NAVEGADOR
    print(f"Abrindo navegador ({NAVEGADOR})...")

    if NAVEGADOR == "edge":
        options = EdgeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--start-maximized")

        perfil_original = r"C:\Users\Francisco\AppData\Local\Microsoft\Edge\User Data"
        perfil_temp = os.path.join(tempfile.gettempdir(), "EdgeSeleniumProfile")
        copiar_perfil_chromium(perfil_original, perfil_temp, "Edge")

        options.add_argument(f"--user-data-dir={perfil_temp}")
        options.add_argument("--profile-directory=Default")
        driver = webdriver.Edge(options=options)

    elif NAVEGADOR == "chrome":
        options = ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--start-maximized")

        perfil_original = r"C:\Users\Francisco\AppData\Local\Google\Chrome\User Data"
        perfil_temp = os.path.join(tempfile.gettempdir(), "ChromeSeleniumProfile")
        copiar_perfil_chromium(perfil_original, perfil_temp, "Chrome")

        options.add_argument(f"--user-data-dir={perfil_temp}")
        options.add_argument("--profile-directory=Default")
        driver = webdriver.Chrome(options=options)

    elif NAVEGADOR == "firefox":
        options = FirefoxOptions()

        perfil_temp = os.path.join(tempfile.gettempdir(), "FirefoxSeleniumProfile")
        perfil = copiar_perfil_firefox(perfil_temp)

        if perfil:
            options.add_argument("-profile")
            options.add_argument(perfil_temp)

        driver = webdriver.Firefox(options=options)
        driver.maximize_window()

    elif NAVEGADOR == "opera":
        # Opera usa ChromeDriver com binario do Opera
        options = ChromeOptions()
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--start-maximized")

        # Encontra o executavel do Opera
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
            print(f"  Usando Opera: {opera_exe}")
        else:
            print("  Opera nao encontrado, tentando iniciar mesmo assim...")

        # Configura perfil
        is_gx = "Opera GX" in (opera_exe or "")
        if is_gx:
            perfil_original = os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera GX Stable")
            perfil_temp = os.path.join(tempfile.gettempdir(), "OperaGXSeleniumProfile")
        else:
            perfil_original = os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera Stable")
            perfil_temp = os.path.join(tempfile.gettempdir(), "OperaSeleniumProfile")

        if os.path.exists(perfil_original):
            copiar_perfil_chromium(perfil_original, perfil_temp, "Opera GX" if is_gx else "Opera", usa_default=False)
            options.add_argument(f"--user-data-dir={perfil_temp}")

        # Detecta versao do Chromium do Opera lendo o arquivo de versao
        chromium_version = None
        try:
            # Opera armazena info de versao no diretorio de instalacao
            opera_dir = os.path.dirname(opera_exe)

            # Tenta ler do Last Version ou VERSION
            for filename in ["Last Version", "VERSION"]:
                version_file = os.path.join(opera_dir, filename)
                if os.path.exists(version_file):
                    with open(version_file, "r") as f:
                        version_str = f.read().strip()
                        if version_str:
                            chromium_version = version_str.split(".")[0]
                            break

            # Se nao encontrou, tenta extrair do user agent padrao
            if not chromium_version:
                # Opera GX geralmente usa Chromium ~10 versoes atras da versao do Opera
                # Mas como o erro mostra 140, vamos usar 140 como padrao para GX
                chromium_version = "140" if is_gx else "131"

        except Exception as e:
            chromium_version = "140"

        print(f"  Versao Chromium detectada: {chromium_version}")

        # Usa webdriver-manager para baixar chromedriver compativel
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service

            print(f"  Baixando ChromeDriver v{chromium_version}...")
            service = Service(ChromeDriverManager(driver_version=f"{chromium_version}").install())
            driver = webdriver.Chrome(service=service, options=options)
        except ImportError:
            print("  AVISO: webdriver-manager nao instalado.")
            print("  Instale com: pip install webdriver-manager")
            print("  Tentando usar driver padrao...")
            driver = webdriver.Chrome(options=options)

    else:
        raise Exception(f"Navegador '{NAVEGADOR}' nao suportado")

    # Acessa o dominio primeiro (necessario para setar cookies)
    driver.get(url)
    time.sleep(1)

    # Injeta cookies
    if isinstance(cookies, list):
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
                print(f"  Cookie '{cookie['name']}' injetado")
            except Exception as e:
                print(f"  Aviso ao injetar cookie: {e}")
    elif isinstance(cookies, dict) and cookies.get("basic_auth"):
        # Para Basic Auth, monta URL com credenciais (encodando caracteres especiais)
        from urllib.parse import urlparse, quote
        parsed = urlparse(url)
        user_encoded = quote(config['username'], safe='')
        pass_encoded = quote(config['password'], safe='')
        auth_url = f"{parsed.scheme}://{user_encoded}:{pass_encoded}@{parsed.netloc}"
        print(f"Usando Basic Auth na URL...")
        driver.get(auth_url)
        return driver
    elif isinstance(cookies, dict) and cookies.get("webfig_autologin"):
        # Para Mikrotik WebFig - login via JavaScript (preenche campos e clica no botao)
        user = json.dumps(config['username'])
        pwd = json.dumps(config['password'])

        print("Preenchendo credenciais via JavaScript...")
        driver.execute_script(f'''
            document.getElementById('name').value = {user};
            document.getElementById('password').value = {pwd};
        ''')

        print("Submetendo login...")
        driver.execute_script('''
            document.querySelector('input[type="submit"]').click();
        ''')

        time.sleep(3)
        return driver

    # Recarrega pagina com autenticacao
    driver.get(url)

    return driver


def login(servico_nome):
    """Realiza login no servico especificado"""

    if servico_nome not in SERVICOS:
        print(f"Servico '{servico_nome}' nao encontrado.")
        print(f"Servicos disponiveis: {', '.join(SERVICOS.keys())}")
        return

    config = SERVICOS[servico_nome]

    print(f"\n{'='*50}")
    print(f"LOGIN VIA API: {servico_nome.upper()}")
    print(f"URL: {config['url']}")
    print(f"{'='*50}\n")

    try:
        # Autentica via API
        if servico_nome == "proxmox":
            cookies = auth_proxmox(config)
        elif servico_nome == "zabbix":
            cookies = auth_zabbix(config)
        elif servico_nome == "mikrotik":
            cookies = auth_mikrotik(config)
        else:
            raise Exception("Servico sem implementacao de API")

        # Abre navegador com sessao
        driver = open_browser(config["url"], cookies, config)

        print(f"\n[OK] Sessao autenticada aberta!")
        print("Mantendo sessao aberta... (feche o navegador para encerrar)\n")

        # Mantem aberto
        while True:
            try:
                _ = driver.title
                time.sleep(2)
            except Exception:
                break

    except Exception as e:
        print(f"\n[ERRO] {e}")
        raise


def menu():
    """Menu interativo"""
    opcoes = {"1": "zabbix", "2": "proxmox", "3": "mikrotik", "0": None}

    while True:
        print("\n" + "="*50)
        print("    LOGIN VIA API - Selecione o servico")
        print("="*50)
        print(f"\n  Navegador: {NAVEGADOR.upper()} (padrao do sistema)")
        print()
        print("  1. Zabbix")
        print("  2. Proxmox")
        print("  3. Mikrotik")
        print("  0. Sair")
        print()

        opcao = input("Escolha uma opcao: ").strip()

        if opcao in opcoes:
            return opcoes[opcao]

        print("Opcao invalida!")


if __name__ == "__main__":
    # Uso: python login_api.py [servico]
    # Exemplo: python login_api.py zabbix

    if len(sys.argv) > 1:
        servico = sys.argv[1].lower()
        login(servico)
    else:
        servico = menu()
        if servico:
            login(servico)
        else:
            print("Saindo...")

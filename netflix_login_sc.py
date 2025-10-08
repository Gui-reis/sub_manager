
# login_and_save_session_auto_robusto.py
# pip install playwright
# playwright install

import os, sys, time, argparse, json
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

NETFLIX_LOGIN_URL = "https://www.netflix.com/login"
NETFLIX_ACCOUNT_URL = "https://www.netflix.com/account/"
NETFLIX_PROFILES_URL = "https://www.netflix.com/account/profiles"
STATE_PATH_DEFAULT = "netflix_state.json"
GRAPHQL_URL = "https://web.prod.cloud.netflix.com/graphql"
PERSISTED_QUERY_ID = "cca89a76-1986-49a9-9c8f-afaa2c098ead"
PERSISTED_QUERY_VERSION = 102

def fill_and_submit_login(page, email, password):
    # Campos (vários seletores para ser resiliente em PT/EN)
    email_input = page.locator(
        'input[name="userLoginId"], input#id_userLoginId, input[data-uia="login-field"], input[type="email"]'
    )
    pwd_input = page.locator(
        'input[name="password"], input#id_password, input[data-uia="password-field"], input[type="password"]'
    )
    submit_btn = page.locator(
        'button[data-uia="login-submit-button"], button[type="submit"]'
    )

    email_input.first.wait_for(state="visible", timeout=30_000)
    pwd_input.first.wait_for(state="visible", timeout=30_000)
    email_input.first.fill(email)
    pwd_input.first.fill(password)
    submit_btn.first.click()

def looks_logged_by_dom(page) -> bool:
    """
    Heurísticas de DOM que aparecem após login:
    - Tela de escolha de perfil (profile-gate)
    - Barra/topo do browse
    - Algum elemento típico da conta
    """
    try:
        # profile gate (grade de perfis)
        if page.locator('[data-uia="profile-chooser"]').first.is_visible():
            return True
        if page.locator('.profile-gate-container, .choose-profile').first.is_visible():
            return True
    except Exception:
        pass
    try:
        # barra do browse
        if page.locator('[data-uia="actionmenu"]').first.is_visible():
            return True
        if page.locator('a[href*="/browse"]').first.is_visible():
            return True
    except Exception:
        pass
    try:
        # página de conta
        if page.url and "/account" in page.url:
            return True
    except Exception:
        pass
    return False

def looks_logged_by_cookies(ctx) -> bool:
    """
    Considera logado se existirem cookies de sessão típicos.
    """
    try:
        cookies = ctx.cookies()
    except Exception:
        return False
    names = {c["name"] for c in cookies}
    # os dois principais
    return ("NetflixId" in names) and ("SecureNetflixId" in names)

def wait_logged(ctx, page, timeout_s=120, poll_s=2, verbose=True) -> bool:
    """
    Faz polling combinando URL, cookies e DOM.
    Retorna True se detectar login dentro do timeout.
    """
    start = time.time()
    last_print = 0
    while time.time() - start < timeout_s:
        url = page.url or ""
        on_login_page = "/login" in url

        by_url = ("/browse" in url) or ("/Profiles" in url) or ("/profiles" in url) or ("/account" in url)
        by_dom = looks_logged_by_dom(page)
        by_ck  = looks_logged_by_cookies(ctx)

        ok = (not on_login_page) and (by_url or by_dom or by_ck)

        now = time.time()
        if verbose and now - last_print > 2:
            print(f"[esperando login] url='{url}'  dom={by_dom}  cookies={by_ck}")
            last_print = now

        if ok:
            return True

        time.sleep(poll_s)
    return False

def build_cookie_header(cookies):
    pairs = []
    for c in cookies:
        dom = c.get("domain","")
        if "netflix.com" in dom:
            pairs.append(f'{c["name"]}={c["value"]}')
    return "; ".join(pairs)

def is_add_profile_page_ready(page, timeout=5000):
    '''Aguarda até que a janela para inserir dados do usuário esteja pronta'''
    
    name_input = page.locator('input[data-uia="account-profiles-page+add-profile+name-input"]')
    name_input.wait_for(state="visible", timeout=timeout)
    
    if not name_input.is_enabled():
        return False

    return True

def was_user_created(page, timeout=500):
    '''Checa se o usuário foi criado'''

    try:
        # aceitamos regex para detectar o query param em qualquer ordem
        import re
        page.wait_for_url(re.compile(r"profileAdded=success"), timeout=int(timeout * 1000))
        return True
    except PWTimeout:
        return False

def create_new_user(ctx, user_name, avatar_key="icon26", is_kids=False):

    page = ctx.new_page()
    print("Abrindo página de login…")
    page.goto(NETFLIX_PROFILES_URL, wait_until="domcontentloaded")

    profile_add_btn = page.locator('button[data-uia="menu-card+button"][data-cl-view="addProfile"]')
    profile_add_btn.wait_for(state="visible")
    profile_add_btn.first.click()

    if is_add_profile_page_ready(page):
        
        name_input = page.locator('input[data-uia="account-profiles-page+add-profile+name-input"]')
        save_btn = page.locator('button[data-uia="account-profiles-page+add-profile+primary-button"]')
        name_input.first.fill(user_name)
        time.sleep(0.1)
        save_btn.first.click()
        return was_user_created(page)
        
def is_session_valid(ctx, account_url, timeout_s=10):
    """Tenta acessar a página de Account e heurísticas simples para decidir se está logado."""
    page = ctx.new_page()
    try:
        # navegar com um timeout razoável (em ms)
        page.goto(account_url, wait_until="networkidle", timeout=timeout_s * 1000)
    except Exception as e:
        # navegacao pode falhar por timeout/redirects; tratar como inválido
        print(f"Aviso: erro ao acessar {account_url}: {e}", file=sys.stderr)
        page.close()
        return False

    # 1) Se o URL final contém /account => muito provável que esteja logado
    final_url = page.url or ""
    if "/account" in final_url:
        page.close()
        return True


def load_context_with_state(browser, state_path):
    
    if state_path != '':
        try:
            return browser.new_context(storage_state=state_path)
        except Exception as e:
            print(f"Aviso: falha ao carregar storage_state ({state_path}): {e}", file=sys.stderr)
            # cai para criar um contexto limpo
    return browser.new_context()


def main():

    ap = argparse.ArgumentParser(description="Login Netflix automatizado e salvar sessão (cookies).")
    ap.add_argument("--email", default=os.getenv("NETFLIX_EMAIL"))
    ap.add_argument("--password", default=os.getenv("NETFLIX_PASSWORD"))
    ap.add_argument("--username")
    ap.add_argument("--state-path", default=STATE_PATH_DEFAULT)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=args.headless)
        ctx = load_context_with_state(browser, args.state_path)

        
        if is_session_valid(ctx, NETFLIX_ACCOUNT_URL, timeout_s=10):
            print('Sessão ainda é valida!')
            
        else:
            
            page = ctx.new_page()
            print("Abrindo página de login…")
            page.goto(NETFLIX_LOGIN_URL, wait_until="domcontentloaded")

            # Se credenciais vierem, preenche e clica; senão, você pode logar manualmente
            if args.email and args.password:
                try:
                    fill_and_submit_login(page, args.email, args.password)
                except PWTimeout:
                    print("Não achei os campos de login. Faça manualmente na janela.", file=sys.stderr)

            if not args.headless:
                print("Se houver 2FA/CAPTCHA, conclua na janela. Eu vou checando a cada 2s…")

            ok = wait_logged(ctx, page, timeout_s=args.timeout, poll_s=2, verbose=True)
            if not ok:
                print("⚠️  Não detectei login dentro do tempo. Se você já está na página de perfis, talvez eu não tenha visto a transição.", file=sys.stderr)

            # Sempre tentar salvar algo
            try:
                ctx.storage_state(path=args.state_path)
                print(f"✅ Sessão salva em: {args.state_path}")
            except Exception as e:
                print("Aviso: storage_state direto falhou, tentando fallback de cookies…", e)
                try:
                    import json
                    state = {"cookies": ctx.cookies(), "origins": []}
                    with open(args.state_path, "w", encoding="utf-8") as f:
                        json.dump(state, f)
                    print(f"✅ Sessão salva (fallback) em: {args.state_path}")
                except Exception as e2:
                    print("❌ Falhou coletar cookies do contexto. Rode de novo sem fechar a janela, por favor.", e2)

            page.close()

        user = create_new_user(ctx, args.username)

        if user:
            print("Usuário criado com sucesso!")

        else:
            print("Falha ao criar user")

            
if __name__ == "__main__":
    main()
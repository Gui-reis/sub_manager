
# login_and_save_session_auto_robusto.py
# pip install playwright
# playwright install

import os, sys, time, argparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

NETFLIX_LOGIN_URL = "https://www.netflix.com/login"
STATE_PATH_DEFAULT = "netflix_state.json"

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

def main():
    ap = argparse.ArgumentParser(description="Login Netflix automatizado e salvar sessão (cookies).")
    ap.add_argument("--email", default=os.getenv("NETFLIX_EMAIL"))
    ap.add_argument("--password", default=os.getenv("NETFLIX_PASSWORD"))
    ap.add_argument("--state-path", default=STATE_PATH_DEFAULT)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        ctx = browser.new_context()
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

        # Opcional: mostra um Cookie header pronto
        try:
            cookies = ctx.cookies()
            print("\n==== Cookie (para usar em requests, se quiser) ====")
            print(build_cookie_header(cookies))
            print("==================================================\n")
        except Exception:
            pass

        browser.close()

if __name__ == "__main__":
    main()
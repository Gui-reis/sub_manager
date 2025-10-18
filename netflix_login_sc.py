
# login_and_save_session_auto_robusto.py
# pip install playwright
# playwright install

import os, sys, time, argparse, json
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import pages


STATE_PATH_DEFAULT = "netflix_state.json"


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
        page = ctx.new_page()
        cfg = pages.PageConfig()

        account_page = pages.AccountPage(page, cfg)
        account_page.open("networkidle")

        # Testa se ainda temos uma sessão valida
        if account_page.is_at() == True:
            print('Sessão ainda é valida!')

        # Se não tivermos, será necessário efetuar o login
        else:

            login_page = pages.LoginPage(page, cfg)
            login_page.open()
            login_page.login(args.email, args.password)
            login_page.wait_logged()

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

        profile_page = pages.ProfilesPage(page, cfg)
        profile_page.open()
        modal = profile_page.click_add()  # clica no botão e instancia o modal
        modal.create(args.username)     # interage dentro do modal (sem trocar de URL)
        ok = profile_page.wait_profile_added()

if __name__ == "__main__":
    main()
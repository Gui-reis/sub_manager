
# login_and_save_session_auto_robusto.py
# pip install playwright
# playwright install

import os, sys, time, argparse, json
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import pages
import Postgres

STATE_PATH_DEFAULT = "netflix_state.json"


def load_context_with_state(browser, state: dict):
    
    context = browser.new_context(storage_state=state)
    return context


def main():

    ap = argparse.ArgumentParser(description="Login Netflix automatizado e salvar sessão (cookies).")
    ap.add_argument("--username")
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()


    # Try to retrieve an available account 
    netflix_db = Postgres.AccountsRepo()
    account = netflix_db.get_first_available()

    if account is None:
        print('Nenhuma conta está disponível para uso')
        return
    
    email = account["email"]
    password = netflix_db.get_plain_password(email)
    session_context = netflix_db.get_storage_state(email)

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=args.headless)
        ctx = (browser.new_context(storage_state=session_context)
         if session_context else browser.new_context())
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
            login_page.login(email, password)
            login_page.wait_logged()

             # Sempre tentar salvar algo
            try:
                state_dict = ctx.storage_state()
                netflix_db.save_storage_state(email, state_dict)
            except Exception as e:
                print("Aviso: insertion do json da sessão falhou...", e)
                

        profile_page = pages.ProfilesPage(page, cfg)
        profile_page.open()
        modal = profile_page.click_add()  # clica no botão e instancia o modal
        modal.create(args.username)     # interage dentro do modal (sem trocar de URL)
        ok = profile_page.wait_profile_added()

        # Caso o user tenha sido adicionado com sucesso, adionamos o novo user na tabela e tratamos da availability.
        if ok:

            user_added = netflix_db.push_back_user(email, args.username)
            if user_added:
                

                # Cria um pin para o user

                # Retorna para o usuário o Pin dele e também a senha atual da conta

    
                # Altera novamente a senha depois de alguns minutos


                if netflix_db.count_users(email) == 2:
                    netflix_db.update_availability(email, False)



if __name__ == "__main__":


     
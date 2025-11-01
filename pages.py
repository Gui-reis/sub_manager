from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import Page, Locator
import re


@dataclass(frozen=True)
class PageConfig:
    base_url: str = "https://www.netflix.com"
    wait_timeout_ms: int = 70_000

@dataclass(frozen=True)
class UiTimeouts:
    ready_ms: int = 5_000
    action_ms: int = 10_000

class BasePage(ABC):
    path: str  # ex.: "/login"
    def __init__(self, page: Page, cfg: PageConfig):
        self.page = page
        self.cfg = cfg

    @property
    def url(self) -> str:
        return f"{self.cfg.base_url}{self.path}"

    def open(self, wait_until: str = "domcontentloaded") -> None:
        self.page.goto(self.url, wait_until=wait_until)
        self.wait_ready()  # Template Method: garante “pronto” após abrir

    @abstractmethod
    def wait_ready(self) -> None:
        """Cada página define o que significa estar pronta (locators visíveis, etc.)."""

    def is_at(self) -> bool:
        """Checagem leve para confirmar que estamos na página esperada."""
        return self.path in (self.page.url or "")


class BaseComponent(ABC):
    def __init__(self, root: Locator, timeouts: UiTimeouts = UiTimeouts()):
        self.root = root
        self.timeouts = timeouts

    @abstractmethod
    def wait_ready(self) -> None:
        ...

class AddProfileModal(BaseComponent):
    INPUT_USERNAME = 'input[data-uia="account-profiles-page+add-profile+name-input"]'
    SAVE_BTN       = 'button[data-uia="account-profiles-page+add-profile+primary-button"]'

    def wait_ready(self) -> None:
        # espera o contêiner e o input do modal ficarem prontos
        self.root.wait_for(state="visible", timeout=self.timeouts.ready_ms)
        self.root.locator(self.INPUT_USERNAME).wait_for(
            state="visible", timeout=self.timeouts.ready_ms
        )

    def create(self, username: str) -> None:
        self.root.locator(self.INPUT_USERNAME).first.fill(username)
        self.root.locator(self.SAVE_BTN).first.click()


class LoginPage(BasePage):

    ''' Seletores CSS'''
    path = "/login"
    EMAIL = 'input[name="userLoginId"], input#id_userLoginId, input[data-uia="login-field"], input[type="email"]'
    PWD   = 'input[name="password"], input#id_password, input[data-uia="password-field"], input[type="password"]'
    SUBMIT= 'button[data-uia="login-submit-button"], button[type="submit"]'
    PROFILE = 'div[data-uia="profile-avatar"]'
    HOME_MENU   = 'a.menu-trigger[data-uia="main-header-menu-trigger"][href="/browse"]'
    HOME_SEARCH = 'svg.search-icon[data-icon="MagnifyingGlassMedium"'


    def wait_ready(self) -> None:
        self.page.locator(self.EMAIL).first.wait_for(state="visible", timeout=self.cfg.wait_timeout_ms)

    def login(self, email: str, password: str) -> None:
        self.page.locator(self.EMAIL).first.fill(email)
        self.page.locator(self.PWD).first.fill(password)
        self.page.locator(self.SUBMIT).first.click()

    def wait_logged(self) -> None:
        
        any_selector = f"{self.PROFILE}, {self.HOME_MENU}, {self.HOME_SEARCH}"
        try:
            self.page.locator(any_selector).first.wait_for(
                state="visible", timeout=self.cfg.wait_timeout_ms
            )

        except:
           
            self.page.wait_for_url(
                re.compile(r"/(browse|profiles?)"),
                timeout=int(self.cfg.wait_timeout_ms * 0.6),
            )
                


class AccountPage(BasePage):
    path = "/account/"
    # seletores específicos aqui (ex.: header da conta)
    def wait_ready(self) -> None:
        # opção: algo leve; se não tiver seletor único, pode ser no-op
        pass

class ProfilesPage(BasePage):
    path = "/account/profiles"
    ADD_BTN = 'button[data-uia="menu-card+button"][data-cl-view="addProfile"]'
    MODAL_ROOT = 'div[data-uia="account-profiles-page+add-profile+background"]'

    def wait_ready(self) -> None:

        self.page.wait_for_load_state("networkidle")
        self.page.locator(self.ADD_BTN).wait_for(state="visible", timeout=self.cfg.wait_timeout_ms)
        
    def click_add(self) -> AddProfileModal:


        self.page.locator(self.ADD_BTN).click()
        root = self.page.locator(self.MODAL_ROOT)
        modal = AddProfileModal(root)
        modal.wait_ready()
        return modal


    def wait_profile_added(self, timeout_s: float = 10.0) -> bool:
        import re
        try:
            self.page.wait_for_url(re.compile(r"profileAdded=success"), timeout=int(timeout_s * 1000))
            return True
        except Exception:
            return False


from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, LargeBinary, JSON, DateTime
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
import getpass
import json

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username="postgres",
    password="Polito9090@",  # sua senha aqui; considere usar variável de ambiente
    host="localhost",
    port=5432,
    database="netflix_accounts",
)

engine = create_engine(DATABASE_URL, echo=False, future=True)  # echo=False para não logar SQL com segredos
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


""" class Base(DeclarativeBase):
    pass

class  accounts(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # BYTEA
    encrypted_pin: Mapped[str  | None] = mapped_column(Text, nullable=True) # se depois virar bytea
    storage_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_checked: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    cookie_valid_until: Mapped[str | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String, default="unknown")
    notes: Mapped[str | None] = mapped_column(Text) """


class AccountsRepo:

    def __init__(self, session_factory: sessionmaker = SessionLocal):
        self._Session = session_factory

    def insert_account_pgcrypto(self, email: str, plain_pw: str) -> None:
        key = getpass.getpass("Chave de criptografia (pgcrypto): ")
        sql = text("""
            INSERT INTO public.accounts (email, encrypted_password, status)
            VALUES (:email, pgp_sym_encrypt(:plain_pw, :key)::bytea, 'ok')
            ON CONFLICT (email) DO UPDATE
            SET encrypted_password = EXCLUDED.encrypted_password,
                status = 'ok'
        """)
        with self._Session() as s, s.begin():
            s.execute(sql, {"email": email, "plain_pw": plain_pw, "key": key})

    def get_plain_password(self, email: str) -> str | None:
        key = getpass.getpass("Chave de criptografia (pgcrypto): ")
        sql = text("""
            SELECT pgp_sym_decrypt(encrypted_password, :key) AS plain_pw
            FROM public.accounts
            WHERE trim(lower(email)) = lower(:email)
        """)
        with self._Session() as s:
            row = s.execute(sql, {"email": email, "key": key}).mappings().first()
            return row and row["plain_pw"]

    def update_availability(self, email: str, availability: bool) -> None:
        sql = text("""
            UPDATE public.accounts
            SET availability = :availability
            WHERE trim(lower(email)) = lower(:email)
        """)
        with self._Session() as s, s.begin():
            s.execute(sql, {"email": email, "availability": availability})

    def get_storage_state(self, email: str) -> dict | None:
        # .columns(JSONB()) ajuda o SQLAlchemy a desserializar em dict
        sql = text("""
            SELECT storage_state
            FROM public.accounts
            WHERE trim(lower(email)) = lower(:email)
        """).columns(storage_state=JSONB())
        with self._Session() as s:
            return s.execute(sql, {"email": email}).scalar_one_or_none()

    def save_storage_state(self, email: str, state: dict) -> None:
        
        sql = text("""
            UPDATE public.accounts
            SET storage_state = :state
            WHERE trim(lower(email)) = lower(:email)
            """).bindparams(bindparam("state", type_=JSONB))

        with self._Session() as s, s.begin():
            s.execute(sql, {"email": email, "state": state})

    def get_first_available(self) -> dict | None:
        sql = text("""
            SELECT id, email, storage_state, availability, last_checked
            FROM public.accounts
            WHERE availability = TRUE
            ORDER BY last_checked NULLS FIRST, id
            LIMIT 1
        """)
        with self._Session() as s:
            row = s.execute(sql).mappings().first()
            return dict(row) if row else None
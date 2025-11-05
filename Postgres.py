from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, LargeBinary, JSON, DateTime
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
import getpass
import json
import os
import stat

from pathlib import Path

DEFAULT_KEY_PATH = Path.home() /".secrets" /"pg_key.txt"

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

    def _read_key_file(self, path: Path) -> str | None:
        try:
            # Certifica que existe
            if not path.exists():
                return None

            # Verifica permissões: idealmente apenas user readable (0o600)
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:  # qualquer permissão para group/other é ruim
                raise PermissionError(
                    f"Key file {path} tem permissões inseguras ({oct(mode)}). "
                    "Defina 0o600: chmod 600 {path}"
                )


            # Lê e strip (remove newline)
            text_key = path.read_text(encoding="utf-8").strip()
            return text_key or None
        except PermissionError:
            print("Permission error")
            raise
        except Exception as e:
            # não vaza exceções sensíveis; logue em debug se precisar
            return None

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

    def get_plain_password(self, email: str, key_path: str | None = None) -> str | None:
        """
        Lê a chave de um ficheiro (key_path ou DEFAULT_KEY_PATH).
        Se não existir, pede via getpass (modo atual).
        """
        # Resolve path do ficheiro (opcional)
        key = None
        if key_path:
            key_file = Path(key_path).expanduser()
            key = self._read_key_file(key_file)
        else:
            key = self._read_key_file(DEFAULT_KEY_PATH)

        # fallback para pedir via getpass (se ainda não encontrou a chave)
        if not key:
            # NÃO imprima a chave em logs!
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

    def push_back_user(self, email: str, value: str, unique: bool = False) -> bool:
        """
        Adiciona 'value' ao final do array 'users'.
        Se unique=True, só adiciona se ainda não existir.
        Retorna True se houve UPDATE (linha afetada), False caso contrário.
        """
        if unique:
            sql = text("""
                UPDATE public.accounts
                SET users = array_append(COALESCE(users, '{}'::text[]), :value)
                WHERE trim(lower(email)) = lower(:email)
                  AND NOT (:value = ANY(COALESCE(users, '{}'::text[])))
            """)
        else:
            sql = text("""
                UPDATE public.accounts
                SET users = array_append(COALESCE(users, '{}'::text[]), :value)
                WHERE trim(lower(email)) = lower(:email)
            """)
        with self._Session() as s, s.begin():
            result = s.execute(sql, {"email": email, "value": value})
            return result.rowcount > 0

    def remove_user(self, email: str, value: str) -> bool:
        """
        Remove 'value' do array 'users'.
        Retorna True se removeu (linha afetada), False se não havia o valor ou email não existe.
        """
        sql = text("""
            UPDATE public.accounts
            SET users = array_remove(COALESCE(users, '{}'::text[]), :value)
            WHERE trim(lower(email)) = lower(:email)
              AND (:value = ANY(COALESCE(users, '{}'::text[])))
        """)
        with self._Session() as s, s.begin():
            result = s.execute(sql, {"email": email, "value": value})
            return result.rowcount > 0

    def count_users(self, email: str) -> int:
        """
        Retorna o número de elementos no array 'users'.
        """
        sql = text("""
            SELECT COALESCE(cardinality(users), 0) AS n
            FROM public.accounts
            WHERE trim(lower(email)) = lower(:email)
        """)
        with self._Session() as s:
            row = s.execute(sql, {"email": email}).mappings().first()
            return int(row["n"]) if row else 0

    def upsert_usercred_encrypted(self, email: str, name: str, plain_secret: str, key_path: str | None = None) -> bool:
        """
        Se existir um par com (name), atualiza somente o secret (recriptografa).
        Senão, adiciona (name, pgp_sym_encrypt(plain_secret, key)).
        Retorna True se houve alteração.
        """
        key = None
        if key_path:
            key_file = Path(key_path).expanduser()
            key = self._read_key_file(key_file)
        else:
            key = self._read_key_file(DEFAULT_KEY_PATH)

        # fallback para pedir via getpass (se ainda não encontrou a chave)
        if not key:
            # NÃO imprima a chave em logs!
            key = getpass.getpass("Chave de criptografia (pgcrypto): ")

        # 1) tenta UPDATE-in-place (substitui apenas o secret de quem tiver name = :name)
        sql_update = text("""
            UPDATE public.accounts
            SET user_creds = ARRAY(
              SELECT ROW((e).name,
                         CASE WHEN (e).name = :name
                              THEN pgp_sym_encrypt(:plain_secret, :key)::bytea
                              ELSE (e).secret END
                  )::public.user_cred
              FROM unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS e
            )
            WHERE trim(lower(email)) = lower(:email)
              AND EXISTS (
                SELECT 1
                FROM unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS ee
                WHERE (ee).name = :name
              )
        """)
        with self._Session() as s, s.begin():
            r1 = s.execute(sql_update, {
                "email": email,
                "name": name,
                "plain_secret": plain_secret,
                "key": key
            })
            if r1.rowcount > 0:
                return True

        # 2) se não existia, faz append
        sql_append = text("""
            UPDATE public.accounts
            SET user_creds = array_append(
                  COALESCE(user_creds, '{}'::public.user_cred[]),
                  ROW(:name, pgp_sym_encrypt(:plain_secret, :key)::bytea)::public.user_cred
                )
            WHERE trim(lower(email)) = lower(:email)
        """)
        with self._Session() as s, s.begin():
            r2 = s.execute(sql_append, {
                "email": email,
                "name": name,
                "plain_secret": plain_secret,
                "key": key
            })
            return r2.rowcount > 0

    def get_usercred_plain(self, email: str, name: str, key_path: str | None = None) -> str | None:
        """
        Retorna o secret (decriptografado) para o par com 'name'.
        """
        key = None
        if key_path:
            key_file = Path(key_path).expanduser()
            key = self._read_key_file(key_file)
        else:
            key = self._read_key_file(DEFAULT_KEY_PATH)

        # fallback para pedir via getpass (se ainda não encontrou a chave)
        if not key:
            # NÃO imprima a chave em logs!
            key = getpass.getpass("Chave de criptografia (pgcrypto): ")


        sql = text("""
            SELECT pgp_sym_decrypt((e).secret, :key) AS plain_secret
            FROM public.accounts
            CROSS JOIN LATERAL unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS e
            WHERE trim(lower(email)) = lower(:email)
              AND (e).name = :name
            LIMIT 1
        """)
        with self._Session() as s:
            row = s.execute(sql, {"email": email, "name": name, "key": key}).mappings().first()
            return row and row["plain_secret"]

    def remove_usercred(self, email: str, name: str, ignore_case: bool = False) -> bool:
        """
        Remove do array user_creds todos os pares cujo (name) corresponda.
        Se ignore_case=True, compara case-insensitive.
        Retorna True se removeu (houve UPDATE), False se não havia o name ou email não existe.
        """
        if ignore_case:
            sql = text("""
                UPDATE public.accounts
                SET user_creds = ARRAY(
                  SELECT e
                  FROM unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS e
                  WHERE lower((e).name) <> lower(:name)
                )
                WHERE trim(lower(email)) = lower(:email)
                  AND EXISTS (
                    SELECT 1
                    FROM unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS ee
                    WHERE lower((ee).name) = lower(:name)
                  )
            """)
        else:
            sql = text("""
                UPDATE public.accounts
                SET user_creds = ARRAY(
                  SELECT e
                  FROM unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS e
                  WHERE (e).name <> :name
                )
                WHERE trim(lower(email)) = lower(:email)
                  AND EXISTS (
                    SELECT 1
                    FROM unnest(COALESCE(user_creds, '{}'::public.user_cred[])) AS ee
                    WHERE (ee).name = :name
                  )
            """)

        with self._Session() as s, s.begin():
            r = s.execute(sql, {"email": email, "name": name})
            return r.rowcount > 0

    def count_usercreds(self, email: str) -> int:
        sql = text("""
            SELECT COALESCE(cardinality(user_creds), 0) AS n
            FROM public.accounts
            WHERE trim(lower(email)) = lower(:email)
        """)
        with self._Session() as s:
            row = s.execute(sql, {"email": email}).mappings().first()
            return int(row["n"]) if row else 0


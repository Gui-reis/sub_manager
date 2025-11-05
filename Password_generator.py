import secrets
import string
from typing import Iterable, Sequence

# -------- Passwords fortes (caracteres) --------
def generate_password(
    length: int = 24,
    use_upper: bool = True,
    use_lower: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    exclude_ambiguous: bool = True,
    require_each_class: bool = True,
) -> str:
    """
    Gera senha criptograficamente forte.
    - exclude_ambiguous: remove chars como 0/O, 1/l/I, etc.
    - require_each_class: garante pelo menos 1 de cada classe escolhida.
    """
    if length < 4 and require_each_class:
        raise ValueError("length mínimo é 4 quando require_each_class=True")

    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*()-_=+[]{};:,.?/\\|~"

    if exclude_ambiguous:
        ambiguous = set("O0o1lI|`'\";:.,")
        upper = "".join(c for c in upper if c not in ambiguous)
        lower = "".join(c for c in lower if c not in ambiguous)
        digits = "".join(c for c in digits if c not in ambiguous)
        # símbolos já são menos ambíguos; mantemos todos acima

    pools = []
    if use_upper:  pools.append(upper)
    if use_lower:  pools.append(lower)
    if use_digits: pools.append(digits)
    if use_symbols:pools.append(symbols)

    if not pools:
        raise ValueError("Selecione ao menos uma classe de caracteres.")

    alphabet = "".join(pools)

    # Se precisa garantir 1 de cada classe:
    chars = []
    if require_each_class:
        for p in pools:
            chars.append(secrets.choice(p))
        # completa o resto
        for _ in range(length - len(chars)):
            chars.append(secrets.choice(alphabet))
        # embaralha para não deixar previsível onde caem as classes obrigatórias
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)

    # caso simples
    return "".join(secrets.choice(alphabet) for _ in range(length))


# -------- Passphrases (palavras) --------
def generate_passphrase(
    wordlist: Sequence[str],
    num_words: int = 6,
    delimiter: str = "-",
    capitalize: bool = False,
) -> str:
    """
    Gera uma passphrase com 'num_words' escolhidas da 'wordlist'.
    Use uma wordlist grande (ex.: EFF/Diceware). Cada palavra deve ser simples (sem espaço).
    """
    if not wordlist:
        raise ValueError("Forneça uma wordlist não vazia.")
    words = []
    for _ in range(num_words):
        w = secrets.choice(wordlist)
        if capitalize:
            w = w.capitalize()
        words.append(w)
    return delimiter.join(words)


# -------- Token URL-safe (útil p/ links temporários, etc.) --------
def generate_token_urlsafe(nbytes: int = 32) -> str:
    """
    Gera um token URL-safe (Base64 modificado), ótimo para reset-links, CSRF, etc.
    nbytes=32 ≈ 256 bits de entropia antes de Base64.
    """
    return secrets.token_urlsafe(nbytes)


# -------- Estimador simples de entropia --------
def estimate_entropy_bits(length: int, alphabet_size: int) -> float:
    """
    Estimativa clássica: length * log2(alphabet_size)
    (útil p/ comparar políticas).
    """
    import math
    return length * math.log2(alphabet_size)

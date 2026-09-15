import base64
import hashlib
import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

KVAULT_MAGIC = "kvault-fernet-1"
PBKDF2_ITERATIONS = 600000
SALT_BYTES = 16


class VaultError(Exception):
    pass


def derive_key(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )


def save_vault(path, vault_data, password):
    if len(password) < 8:
        raise VaultError("Пароль должен содержать не менее 8 символов")
    salt = secrets.token_bytes(SALT_BYTES)
    fernet = Fernet(base64.urlsafe_b64encode(derive_key(password, salt)))
    token = fernet.encrypt(json.dumps(vault_data, ensure_ascii=False).encode("utf-8"))
    blob = {
        "format": KVAULT_MAGIC,
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
    }
    Path(path).write_text(json.dumps(blob, indent=1), encoding="utf-8")


def load_vault(path, password):
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise VaultError(f"Не удалось прочитать файл-ключ: {e}") from e
    if not isinstance(blob, dict) or blob.get("format") != KVAULT_MAGIC:
        raise VaultError("Это не файл-ключ анонимизатора (.kvault)")
    try:
        salt = base64.b64decode(blob["salt"], validate=True)
        fernet = Fernet(base64.urlsafe_b64encode(derive_key(password, salt)))
        plain = fernet.decrypt(blob["token"].encode("ascii"))
    except (KeyError, ValueError, InvalidToken) as e:
        raise VaultError("Неверный пароль или повреждённый файл-ключ") from e
    try:
        data = json.loads(plain.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise VaultError("Повреждённое содержимое файла-ключа") from e
    if data.get("format") != "kvault-1":
        raise VaultError("Неподдерживаемая версия формата файла-ключа")
    return data

from pwdlib import PasswordHash
from typing import Protocol

password_hash = PasswordHash.recommended()


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hash.verify(password, stored_hash)

class AuthRepository(Protocol):
    def get_password_hash(self, login: str) -> str | None:
        ...


def authenticate_user(
    login: str,
    password: str,
    repository: AuthRepository,
) -> bool:
    stored_hash = repository.get_password_hash(login)

    if stored_hash is None:
        return False

    return verify_password(password, stored_hash)

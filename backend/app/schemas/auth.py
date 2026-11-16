from pydantic import BaseModel, SecretStr


class LoginRequest(BaseModel):
    login: str
    password: SecretStr


class LoginResponse(BaseModel):
    authenticated: bool

import re

from pydantic import BaseModel, field_validator


class StorageConfig(BaseModel):
    mode: str
    cifs_host: str | None = None
    cifs_share: str | None = None
    cifs_username: str | None = None
    cifs_subpath: str | None = None


class SetCifsStorageRequest(BaseModel):
    host: str
    share: str
    username: str
    password: str
    subpath: str = ""

    @field_validator("host")
    @classmethod
    def host_no_special(cls, v: str) -> str:
        # Permite IPs, hostnames e FQDNs; rejeita caracteres de injeção de comando
        if not re.match(r"^[A-Za-z0-9._-]+$", v):
            raise ValueError("host inválido: use apenas letras, números, '.', '-' e '_'")
        return v

    @field_validator("share")
    @classmethod
    def share_no_special(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9 ._-]+$", v):
            raise ValueError("share inválido: use apenas letras, números, espaços, '.', '-' e '_'")
        return v

    @field_validator("subpath")
    @classmethod
    def subpath_no_traversal(cls, v: str) -> str:
        if not v:
            return v
        # Rejeita caminhos absolutos e traversal (..)
        if v.startswith("/") or v.startswith("\\"):
            raise ValueError("subpath não pode ser absoluto")
        if ".." in v.split("/") or ".." in v.split("\\"):
            raise ValueError("subpath não pode conter '..'")
        return v

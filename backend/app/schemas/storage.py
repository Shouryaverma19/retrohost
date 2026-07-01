from pydantic import BaseModel


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

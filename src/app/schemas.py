from typing import Optional, Any
from pydantic import BaseModel


class SendCodeRequest(BaseModel):
    phone: str


class SubmitCodeRequest(BaseModel):
    phone: str
    code: str


class SubmitPasswordRequest(BaseModel):
    phone: str
    password: str


class AuthStatus(BaseModel):
    logged_in: bool
    phone: Optional[str] = None
    first_name: Optional[str] = None
    username: Optional[str] = None


class DialogOut(BaseModel):
    id: str
    name: str
    type: str
    unread_count: int = 0
    entity_id: int


class StorageTargetIn(BaseModel):
    name: str
    type: str  # "local" | "sftp"
    config: dict[str, Any]
    is_default: bool = False


class StorageTargetOut(BaseModel):
    id: int
    name: str
    type: str
    is_default: bool


class CreateDownloadJob(BaseModel):
    dialog_id: str
    dialog_name: Optional[str] = None
    storage_target_id: Optional[int] = None
    media_types: list[str] = ["photo", "video", "document", "audio", "voice"]
    limit: Optional[int] = None
    min_id: int = 0
    max_id: int = 0
    subfolder: Optional[str] = None


class CreateExportJob(BaseModel):
    dialog_id: str
    dialog_name: Optional[str] = None
    storage_target_id: Optional[int] = None
    format: str = "json"  # json | csv | html
    limit: Optional[int] = None


class CreateForwardJob(BaseModel):
    dialog_id: str
    dialog_name: Optional[str] = None
    target_dialog_id: str
    target_dialog_name: Optional[str] = None
    media_types: list[str] = []  # empty = forward everything, not just media
    limit: Optional[int] = None
    confirm_tos: bool = False


class JobOut(BaseModel):
    id: int
    job_type: str
    dialog_id: str
    dialog_name: Optional[str]
    status: str
    progress: int
    total: int
    output_path: Optional[str]
    error: Optional[str]

    class Config:
        from_attributes = True

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
    date_from: Optional[str] = None  # ISO date/datetime, inclusive
    date_to: Optional[str] = None    # ISO date/datetime, inclusive
    subfolder: Optional[str] = None


class CreateExportJob(BaseModel):
    dialog_id: str
    dialog_name: Optional[str] = None
    storage_target_id: Optional[int] = None
    format: str = "json"  # json | csv | html
    limit: Optional[int] = None


class CreateTransferJob(BaseModel):
    """Unified entry point covering the three supported actions: download
    only (no forward), forward only (server-to-server, nothing saved
    locally), or both — which creates one job of each kind against the same
    filters."""
    dialog_id: str
    dialog_name: Optional[str] = None
    action: str  # "download" | "forward" | "both"
    storage_target_id: Optional[int] = None       # used by download/both
    target_dialog_id: Optional[str] = None         # required by forward/both
    target_dialog_name: Optional[str] = None
    media_types: list[str] = []
    limit: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    confirm_tos: bool = False                      # required by forward/both
    remove_forward_tag: bool = True                 # strip "Forwarded from X" attribution


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
    failed_count: int = 0

    class Config:
        from_attributes = True

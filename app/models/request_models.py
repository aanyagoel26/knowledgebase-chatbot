from pydantic import BaseModel


class RetrieveRequest(BaseModel):
    question: str
    document_ids: list[int] = []


class ChatRequest(BaseModel):
    question: str
    session_id: int | None = None
    document_ids: list[int] = []


class DBChatRequest(BaseModel):
    question: str
    session_id: int | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    department: str | None = None


class FolderRequest(BaseModel):
    folder_path: str


class SessionTitleRequest(BaseModel):
    title: str


class SessionPinRequest(BaseModel):
    is_pinned: bool


class SessionArchiveRequest(BaseModel):
    is_archived: bool

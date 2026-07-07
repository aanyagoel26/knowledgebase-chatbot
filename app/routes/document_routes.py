from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile

from app.models.request_models import FolderRequest
from app.services.auth_service import require_login
from app.services.document_service_api import (
    handle_clear_all_documents,
    handle_download_document,
    handle_get_documents,
    handle_get_knowledge_folder,
    handle_index_now,
    handle_index_status,
    handle_set_knowledge_folder,
    handle_upload_files
)

router = APIRouter()


@router.get("/knowledge-folder")
def get_knowledge_folder(request: Request):
    require_login(request)
    return handle_get_knowledge_folder()


@router.post("/set-knowledge-folder")
def set_knowledge_folder(
        request: FolderRequest,
        http_request: Request):

    require_login(http_request)
    return handle_set_knowledge_folder(request.folder_path)


@router.post("/index-now")
def index_now(
        request: Request,
        background_tasks: BackgroundTasks,
        force: bool = False):

    require_login(request)
    return handle_index_now(background_tasks, force)


@router.get("/index-status")
def index_status(request: Request):
    require_login(request)
    return handle_index_status()


@router.post("/upload")
async def upload_files(
        request: Request,
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File(...)):

    require_login(request)
    return await handle_upload_files(background_tasks, files)


@router.get("/documents")
def get_documents(request: Request):
    require_login(request)
    return handle_get_documents()


@router.delete("/documents/clear")
def clear_all_documents(request: Request):
    require_login(request)
    return handle_clear_all_documents()


@router.get("/download-document/{document_id}")
def download_document(
        document_id: int,
        request: Request):

    require_login(request)
    return handle_download_document(document_id)
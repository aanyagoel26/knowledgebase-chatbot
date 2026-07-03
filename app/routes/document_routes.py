import os
import shutil
import uuid

from fastapi import APIRouter, UploadFile, File, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from models import FolderRequest
from app.services.auth_service import require_login
from app.database.connection import get_db_connection

from app.database.repository import (
    get_all_documents,
    get_document_by_id,
    clear_document_tables,
    get_index_status_counts,
    set_app_setting,
    get_document_by_file_hash
)

from app.services.document_service import (
    is_supported_file,
    calculate_file_hash
)

from app.services.indexing_service import (
    queue_file_for_indexing,
    process_document_indexing,
    scan_knowledge_base_once,
    ensure_folders,
    get_knowledge_base_folder,
    set_knowledge_base_folder,
    is_indexing_running
)

router = APIRouter()


@router.get("/knowledge-folder")
def get_knowledge_folder(request: Request):
    require_login(request)
    return {"folder_path": get_knowledge_base_folder()}


@router.post("/set-knowledge-folder")
def set_knowledge_folder(request: FolderRequest, http_request: Request):
    require_login(http_request)

    folder_path = request.folder_path.strip()

    if not os.path.isdir(folder_path):
        return {
            "success": False,
            "message": "Folder path does not exist.",
            "folder_path": folder_path
        }

    set_knowledge_base_folder(folder_path)
    set_app_setting("knowledge_base_folder", folder_path)
    ensure_folders()

    return {
        "success": True,
        "message": "Knowledge folder saved successfully.",
        "folder_path": get_knowledge_base_folder()
    }


@router.post("/index-now")
def index_now(request: Request, background_tasks: BackgroundTasks, force: bool = False):
    require_login(request)

    background_tasks.add_task(scan_knowledge_base_once, force)

    return {
        "message": "Manual indexing started in background.",
        "force": force
    }


@router.get("/index-status")
def index_status(request: Request):
    require_login(request)

    rows = get_index_status_counts()

    counts = {
        "pending": 0,
        "indexing": 0,
        "ready": 0,
        "failed": 0
    }

    for status, count in rows:
        counts[status or "ready"] = count

    running = counts["pending"] > 0 or counts["indexing"] > 0

    return {
        "running": running,
        "completed": not running,
        "pending": counts["pending"],
        "indexing": counts["indexing"],
        "ready": counts["ready"],
        "failed": counts["failed"]
    }


@router.post("/upload")
async def upload_files(
        request: Request,
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File(...)):

    require_login(request)
    ensure_folders()

    results = []

    if not files:
        return {
            "message": "No files received.",
            "results": []
        }

    for file in files:
        filename = os.path.basename(file.filename)

        if not filename:
            results.append({
                "filename": "unknown",
                "status": "invalid",
                "message": "Invalid filename.",
                "scheduled": False
            })
            continue

        if not is_supported_file(filename):
            results.append({
                "filename": filename,
                "status": "unsupported",
                "message": "Unsupported file type.",
                "scheduled": False
            })
            continue

        final_path = os.path.join(get_knowledge_base_folder(), filename)
        temp_filename = f".uploading_{uuid.uuid4().hex}_{filename}"
        temp_path = os.path.join(get_knowledge_base_folder(), temp_filename)

        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_hash = calculate_file_hash(temp_path)

            existing_duplicate = get_document_by_file_hash(uploaded_hash)

            if existing_duplicate:
                os.remove(temp_path)

                results.append({
                    "filename": filename,
                    "document_id": existing_duplicate[0],
                    "status": "skipped_duplicate",
                    "message": "This file already exists in the knowledge base.",
                    "scheduled": False
                })
                continue

            if os.path.exists(final_path):
                os.remove(final_path)

            shutil.move(temp_path, final_path)

            result = queue_file_for_indexing(
                file_path=final_path,
                source_type="uploaded",
                force_reindex=False
            )

            results.append(result)

            if result["scheduled"]:
                background_tasks.add_task(
                    process_document_indexing,
                    result["document_id"],
                    os.path.abspath(final_path)
                )

        except Exception as error:
            if os.path.exists(temp_path):
                os.remove(temp_path)

            results.append({
                "filename": filename,
                "status": "failed",
                "message": str(error),
                "scheduled": False
            })

    return {
        "message": "Upload completed.",
        "results": results
    }


@router.get("/documents")
def get_documents(request: Request):
    require_login(request)

    rows = get_all_documents()
    documents = []

    for row in rows:
        documents.append({
            "document_id": row[0],
            "filename": row[1],
            "version": row[2],
            "indexing_status": row[3],
            "chunks": row[4],
            "error_message": row[5]
        })

    return {"documents": documents}


@router.delete("/documents/clear")
def clear_all_documents(request: Request):
    require_login(request)

    if is_indexing_running():
        raise HTTPException(
            status_code=409,
            detail="Indexing is currently running. Please wait until it finishes."
        )

    deleted_files = 0
    folder_path = get_knowledge_base_folder()

    if os.path.isdir(folder_path):
        for root, dirs, files in os.walk(folder_path):
            for filename in files:
                file_path = os.path.join(root, filename)

                if is_supported_file(file_path) or filename.startswith(".uploading_"):
                    try:
                        os.remove(file_path)
                        deleted_files += 1
                    except Exception:
                        pass

    clear_document_tables()

    return {
        "message": "All documents, indexed chunks, and uploaded files have been cleared.",
        "deleted_files": deleted_files
    }


@router.get("/download-document/{document_id}")
def download_document(document_id: int, request: Request):
    require_login(request)

    row = get_document_by_id(document_id)

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    filename = row[0]
    file_path = row[1]

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File missing on disk."
        )

    return FileResponse(
        path=file_path,
        filename=filename
    )
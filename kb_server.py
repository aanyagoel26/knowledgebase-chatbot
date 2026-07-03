import os
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.config.settings import (
    AUTO_SCAN_INTERVAL_SECONDS,
    KNOWLEDGE_BASE_FOLDER as DEFAULT_KNOWLEDGE_BASE_FOLDER,
    UI_FILE
)

from app.database.schema import ensure_schema_updates
from app.database.repository import get_app_setting

from app.services.indexing_service import (
    set_knowledge_base_folder,
    get_knowledge_base_folder,
    ensure_folders,
    hourly_knowledge_base_watcher
)

from app.routes.auth_routes import router as auth_router
from app.routes.document_routes import router as document_router
from app.routes.chat_routes import router as chat_router
from app.routes.database_routes import router as database_router
from app.routes.session_routes import router as session_router


app = FastAPI()

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(chat_router)
app.include_router(database_router)
app.include_router(session_router)


def load_knowledge_folder_from_db():
    saved_folder = get_app_setting(
        "knowledge_base_folder",
        DEFAULT_KNOWLEDGE_BASE_FOLDER
    )

    set_knowledge_base_folder(saved_folder)


@app.on_event("startup")
def startup_event():
    ensure_schema_updates()
    load_knowledge_folder_from_db()
    ensure_folders()

    print("\n" + "=" * 80)
    print("KB CHATBOT STARTED")
    print("=" * 80)
    print("Knowledge folder:", os.path.abspath(get_knowledge_base_folder()))
    print("Automatic scan interval:", AUTO_SCAN_INTERVAL_SECONDS, "seconds")

    watcher_thread = threading.Thread(
        target=hourly_knowledge_base_watcher,
        daemon=True
    )

    watcher_thread.start()


@app.get("/")
def home():
    return FileResponse(UI_FILE)


@app.get("/health")
def health_check():
    return {
        "status": "Backend is running"
    }
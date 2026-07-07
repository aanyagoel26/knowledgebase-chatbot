import os
import threading

from app.config.settings import (
    AUTO_SCAN_INTERVAL_SECONDS,
    KNOWLEDGE_BASE_FOLDER as DEFAULT_KNOWLEDGE_BASE_FOLDER
)
from app.core.logger import logger
from app.database.repository import get_app_setting
from app.database.schema import ensure_schema_updates
from app.services.indexing_service import (
    ensure_folders,
    get_knowledge_base_folder,
    hourly_knowledge_base_watcher,
    set_knowledge_base_folder
)


def load_knowledge_folder_from_db():
    saved_folder = get_app_setting(
        "knowledge_base_folder",
        DEFAULT_KNOWLEDGE_BASE_FOLDER
    )

    set_knowledge_base_folder(saved_folder)


def startup_event():
    ensure_schema_updates()
    load_knowledge_folder_from_db()
    ensure_folders()

    print("\n" + "=" * 80)
    print("KB CHATBOT STARTED")
    print("=" * 80)
    logger.info("Knowledge folder: %s", os.path.abspath(get_knowledge_base_folder()))
    logger.info("Automatic scan interval: %s seconds", AUTO_SCAN_INTERVAL_SECONDS)

    watcher_thread = threading.Thread(
        target=hourly_knowledge_base_watcher,
        daemon=True
    )

    watcher_thread.start()
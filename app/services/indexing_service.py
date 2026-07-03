import os
import threading
import time

from psycopg2.extras import execute_values

from app.database.connection import get_db_connection
from app.config.settings import (
    AUTO_SCAN_INTERVAL_SECONDS,
    EMBEDDING_BATCH_SIZE
)
from app.services.document_service import (
    calculate_file_hash,
    get_file_metadata,
    clean_text,
    tokenize,
    extract_text,
    is_supported_file,
    split_text_into_chunks
)
from app.services.embedding_service import generate_embeddings_batch


scan_lock = threading.Lock()

KNOWLEDGE_BASE_FOLDER = "knowledge_base"
UPLOAD_FOLDER = KNOWLEDGE_BASE_FOLDER


def set_knowledge_base_folder(folder_path):
    global KNOWLEDGE_BASE_FOLDER
    global UPLOAD_FOLDER

    KNOWLEDGE_BASE_FOLDER = folder_path
    UPLOAD_FOLDER = folder_path


def get_knowledge_base_folder():
    return KNOWLEDGE_BASE_FOLDER


def ensure_folders():
    os.makedirs(KNOWLEDGE_BASE_FOLDER, exist_ok=True)


def is_indexing_running():
    return scan_lock.locked()


def update_document_status(
        document_id,
        status,
        error_message=None,
        chunk_count=None):

    conn = get_db_connection()
    cursor = conn.cursor()

    if status == "ready":
        cursor.execute(
            """
            UPDATE documents
            SET indexing_status=%s,
                error_message=%s,
                chunk_count=%s,
                indexed_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE document_id=%s
            """,
            (
                status,
                error_message,
                chunk_count,
                document_id
            )
        )
    else:
        cursor.execute(
            """
            UPDATE documents
            SET indexing_status=%s,
                error_message=%s,
                chunk_count=COALESCE(%s,chunk_count),
                updated_at=CURRENT_TIMESTAMP
            WHERE document_id=%s
            """,
            (
                status,
                error_message,
                chunk_count,
                document_id
            )
        )

    conn.commit()
    cursor.close()
    conn.close()


def queue_file_for_indexing(
        file_path,
        source_type,
        force_reindex=False):

    absolute_path = os.path.abspath(file_path)
    original_filename = os.path.basename(file_path)
    metadata = get_file_metadata(file_path)
    file_hash = calculate_file_hash(file_path)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            document_id,
            file_hash,
            file_size,
            version,
            indexing_status
        FROM documents
        WHERE file_path=%s
        """,
        (absolute_path,)
    )

    existing_by_path = cursor.fetchone()

    if existing_by_path:
        (
            document_id,
            old_hash,
            old_size,
            old_version,
            old_status
        ) = existing_by_path

        unchanged = (
            old_hash == file_hash
            and old_size == metadata["file_size"]
        )

        if unchanged and old_status == "ready" and not force_reindex:
            cursor.close()
            conn.close()

            return {
                "filename": original_filename,
                "document_id": document_id,
                "status": "skipped_unchanged",
                "message": "File already indexed.",
                "scheduled": False
            }

        if old_status in ["pending", "indexing"]:
            cursor.close()
            conn.close()

            return {
                "filename": original_filename,
                "document_id": document_id,
                "status": "already_processing",
                "message": "Already processing.",
                "scheduled": False
            }

        new_version = old_version

        if old_hash != file_hash or force_reindex:
            new_version += 1

        cursor.execute(
            """
            UPDATE documents
            SET file_hash=%s,
                file_size=%s,
                last_modified=%s,
                version=%s,
                source_type=%s,
                indexing_status='pending',
                error_message=NULL,
                chunk_count=0,
                updated_at=CURRENT_TIMESTAMP
            WHERE document_id=%s
            """,
            (
                file_hash,
                metadata["file_size"],
                metadata["last_modified"],
                new_version,
                source_type,
                document_id
            )
        )

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "filename": original_filename,
            "document_id": document_id,
            "status": "queued_for_reindexing",
            "message": "Re-indexing started.",
            "scheduled": True
        }

    cursor.execute(
        """
        SELECT document_id
        FROM documents
        WHERE file_hash=%s
        """,
        (file_hash,)
    )

    existing_by_hash = cursor.fetchone()

    if existing_by_hash and not force_reindex:
        cursor.close()
        conn.close()

        return {
            "filename": original_filename,
            "document_id": existing_by_hash[0],
            "status": "skipped_duplicate",
            "message": "File already exists.",
            "scheduled": False
        }

    cursor.execute(
        """
        INSERT INTO documents
        (
            original_filename,
            file_path,
            file_hash,
            file_size,
            last_modified,
            source_type,
            indexing_status,
            chunk_count
        )
        VALUES
        (%s,%s,%s,%s,%s,%s,'pending',0)
        RETURNING document_id
        """,
        (
            original_filename,
            absolute_path,
            file_hash,
            metadata["file_size"],
            metadata["last_modified"],
            source_type
        )
    )

    document_id = cursor.fetchone()[0]

    conn.commit()
    cursor.close()
    conn.close()

    return {
        "filename": original_filename,
        "document_id": document_id,
        "status": "queued_new_document",
        "message": "Queued successfully.",
        "scheduled": True
    }


def process_document_indexing(document_id, file_path):
    print("\n" + "=" * 80)
    print("BACKGROUND INDEXING STARTED")
    print("=" * 80)
    print("Document ID:", document_id)
    print("File:", file_path)

    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError("File not found on server.")

        update_document_status(
            document_id=document_id,
            status="indexing",
            error_message=None,
            chunk_count=0
        )

        extracted_text = extract_text(file_path)
        extracted_text = clean_text(extracted_text)

        chunks = split_text_into_chunks(extracted_text)

        print("Characters extracted:", len(extracted_text))
        print("Chunks created:", len(chunks))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM document_chunks
            WHERE document_id=%s
            """,
            (document_id,)
        )

        inserted_count = 0

        for batch_start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch_chunks = chunks[
                batch_start:batch_start + EMBEDDING_BATCH_SIZE
            ]

            print(
                "Embedding batch",
                batch_start + 1,
                "to",
                batch_start + len(batch_chunks),
                "of",
                len(chunks)
            )

            embeddings = generate_embeddings_batch(batch_chunks)

            rows = []

            for index, chunk in enumerate(batch_chunks):
                chunk_number = batch_start + index + 1
                embedding = embeddings[index]

                rows.append(
                    (
                        document_id,
                        chunk_number,
                        chunk,
                        str(embedding),
                        len(tokenize(chunk))
                    )
                )

            execute_values(
                cursor,
                """
                INSERT INTO document_chunks
                (
                    document_id,
                    chunk_number,
                    content,
                    embedding,
                    token_count
                )
                VALUES %s
                """,
                rows,
                template="(%s,%s,%s,%s::vector,%s)"
            )

            conn.commit()
            inserted_count += len(rows)

        cursor.close()
        conn.close()

        update_document_status(
            document_id=document_id,
            status="ready",
            error_message=None,
            chunk_count=inserted_count
        )

        print("\nBACKGROUND INDEXING COMPLETED")
        print("Document ID:", document_id)
        print("Chunks inserted:", inserted_count)

    except Exception as error:
        error_text = str(error)

        print("\nBACKGROUND INDEXING FAILED")
        print("Document ID:", document_id)
        print(error_text)

        update_document_status(
            document_id=document_id,
            status="failed",
            error_message=error_text,
            chunk_count=0
        )


def cleanup_deleted_files():
    print("\nChecking deleted files...")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id, file_path
        FROM documents
        """
    )

    rows = cursor.fetchall()
    deleted_count = 0

    for document_id, file_path in rows:
        if not os.path.exists(file_path):
            print("Removing deleted file:", file_path)

            cursor.execute(
                """
                DELETE FROM documents
                WHERE document_id=%s
                """,
                (document_id,)
            )

            deleted_count += 1

    conn.commit()
    cursor.close()
    conn.close()

    print("Deleted documents removed:", deleted_count)


def scan_knowledge_base_once(force_reindex=False):
    if scan_lock.locked():
        print("Scan already running.")
        return []

    results = []

    with scan_lock:
        ensure_folders()
        cleanup_deleted_files()

        print("\nSCANNING KNOWLEDGE BASE")
        print(os.path.abspath(KNOWLEDGE_BASE_FOLDER))

        for root, dirs, files in os.walk(KNOWLEDGE_BASE_FOLDER):
            for filename in files:
                file_path = os.path.join(root, filename)

                if not is_supported_file(file_path):
                    continue

                result = queue_file_for_indexing(
                    file_path=file_path,
                    source_type="knowledge_base",
                    force_reindex=force_reindex
                )

                results.append(result)
                print(result)

                if result["scheduled"]:
                    process_document_indexing(
                        result["document_id"],
                        os.path.abspath(file_path)
                    )

    return results


def hourly_knowledge_base_watcher():
    print("\nHourly watcher started")
    print("Folder:", os.path.abspath(KNOWLEDGE_BASE_FOLDER))

    while True:
        time.sleep(AUTO_SCAN_INTERVAL_SECONDS)

        try:
            print("\nRunning automatic hourly scan...")
            scan_knowledge_base_once(False)

        except Exception as error:
            print("Hourly watcher error")
            print(error)
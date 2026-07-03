from app.database.connection import get_db_connection


def get_app_setting(key, default_value=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT setting_value
        FROM app_settings
        WHERE setting_key = %s
        """,
        (key,)
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if row:
        return row[0]

    return default_value


def set_app_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO app_settings(setting_key, setting_value)
        VALUES (%s, %s)
        ON CONFLICT(setting_key)
        DO UPDATE SET
            setting_value = EXCLUDED.setting_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value)
    )

    conn.commit()
    cursor.close()
    conn.close()

# ============================================================
# DOCUMENT REPOSITORY
# ============================================================

def get_all_documents():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            document_id,
            original_filename,
            version,
            indexing_status,
            chunk_count,
            error_message
        FROM documents
        ORDER BY updated_at DESC
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows


def get_document_by_id(document_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            original_filename,
            file_path
        FROM documents
        WHERE document_id=%s
    """, (document_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row


def get_index_status_counts():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT indexing_status, COUNT(*)
        FROM documents
        GROUP BY indexing_status
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows


def clear_document_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        TRUNCATE TABLE
            document_chunks,
            documents
        RESTART IDENTITY CASCADE
    """)

    conn.commit()

    cursor.close()
    conn.close()

# ============================================================
# CHAT REPOSITORY
# ============================================================

def get_chat_sessions(employee_id, assistant_mode):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            session_id,
            title,
            created_at
        FROM chat_sessions
        WHERE employee_id=%s
          AND assistant_mode=%s
        ORDER BY created_at DESC
        """,
        (
            employee_id,
            assistant_mode
        )
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows


def user_owns_session(session_id, employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT session_id
        FROM chat_sessions
        WHERE session_id=%s
          AND employee_id=%s
        """,
        (
            session_id,
            employee_id
        )
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row is not None


def get_chat_messages(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            role,
            message,
            created_at,
            sources_json
        FROM chat_messages
        WHERE session_id=%s
        ORDER BY created_at ASC
        """,
        (session_id,)
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows
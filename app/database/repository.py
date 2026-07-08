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
            created_at,
            COALESCE(is_pinned, FALSE) AS is_pinned,
            COALESCE(is_archived, FALSE) AS is_archived
        FROM chat_sessions
        WHERE employee_id=%s
          AND assistant_mode=%s
          AND COALESCE(is_archived, FALSE) = FALSE
        ORDER BY
            COALESCE(is_pinned, FALSE) DESC,
            updated_at DESC,
            created_at DESC
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
            sources_json,
            answer_payload_json
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

def upsert_employee_after_login(employee, password_hash):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO employees
        (
            name,
            email,
            password_hash,
            role,
            department,
            is_active
        )
        VALUES (%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT(email)
        DO UPDATE SET
            name=EXCLUDED.name,
            role=EXCLUDED.role,
            department=EXCLUDED.department,
            is_active=TRUE
        RETURNING employee_id
        """,
        (
            employee["name"],
            employee["email"],
            password_hash,
            employee.get("role", "employee"),
            employee.get("department")
        )
    )

    employee_id = cursor.fetchone()[0]

    conn.commit()
    cursor.close()
    conn.close()

    return employee_id


def create_employee_session(employee_id, email, session_token, ip_address):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM employee_sessions
        WHERE employee_id=%s
        """,
        (employee_id,)
    )

    cursor.execute(
        """
        UPDATE employee_login_logs
        SET logout_time=CURRENT_TIMESTAMP,
            status='logged_out'
        WHERE employee_id=%s
          AND logout_time IS NULL
        """,
        (employee_id,)
    )

    cursor.execute(
        """
        INSERT INTO employee_sessions(employee_id, session_token)
        VALUES (%s,%s)
        """,
        (employee_id, session_token)
    )

    cursor.execute(
        """
        INSERT INTO employee_login_logs(employee_id, email, ip_address, status)
        VALUES (%s,%s,%s,'active')
        """,
        (employee_id, email, ip_address)
    )

    conn.commit()
    cursor.close()
    conn.close()


def logout_employee_session(session_token):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT e.employee_id, e.email
        FROM employee_sessions s
        JOIN employees e
        ON s.employee_id=e.employee_id
        WHERE s.session_token=%s
        """,
        (session_token,)
    )

    row = cursor.fetchone()

    if row:
        cursor.execute(
            """
            UPDATE employee_login_logs
            SET logout_time=CURRENT_TIMESTAMP,
                status='logged_out'
            WHERE employee_id=%s
              AND email=%s
              AND logout_time IS NULL
            """,
            (row[0], row[1])
        )

    cursor.execute(
        """
        DELETE FROM employee_sessions
        WHERE session_token=%s
        """,
        (session_token,)
    )

    conn.commit()
    cursor.close()
    conn.close()


def create_employee_account(name, email, password_hash, department=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT employee_id
        FROM employees
        WHERE email=%s
        """,
        (email,)
    )

    existing = cursor.fetchone()

    if existing:
        cursor.close()
        conn.close()
        return None

    cursor.execute(
        """
        INSERT INTO employees
        (
            name,
            email,
            password_hash,
            role,
            department,
            is_active
        )
        VALUES (%s,%s,%s,'employee',%s,TRUE)
        RETURNING employee_id
        """,
        (
            name,
            email,
            password_hash,
            department
        )
    )

    employee_id = cursor.fetchone()[0]

    conn.commit()
    cursor.close()
    conn.close()

    return employee_id


def update_chat_session_title(session_id, employee_id, title):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE chat_sessions
        SET title=%s,
            updated_at=CURRENT_TIMESTAMP
        WHERE session_id=%s
          AND employee_id=%s
        """,
        (
            title,
            session_id,
            employee_id
        )
    )

    updated = cursor.rowcount

    conn.commit()
    cursor.close()
    conn.close()

    return updated > 0


def update_chat_session_pin(session_id, employee_id, is_pinned):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE chat_sessions
        SET is_pinned=%s,
            updated_at=CURRENT_TIMESTAMP
        WHERE session_id=%s
          AND employee_id=%s
        """,
        (
            is_pinned,
            session_id,
            employee_id
        )
    )

    updated = cursor.rowcount

    conn.commit()
    cursor.close()
    conn.close()

    return updated > 0


def update_chat_session_archive(session_id, employee_id, is_archived):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE chat_sessions
        SET is_archived=%s,
            updated_at=CURRENT_TIMESTAMP
        WHERE session_id=%s
          AND employee_id=%s
        """,
        (
            is_archived,
            session_id,
            employee_id
        )
    )

    updated = cursor.rowcount

    conn.commit()
    cursor.close()
    conn.close()

    return updated > 0


def delete_chat_session(session_id, employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM chat_sessions
        WHERE session_id=%s
          AND employee_id=%s
        """,
        (
            session_id,
            employee_id
        )
    )

    deleted = cursor.rowcount

    conn.commit()
    cursor.close()
    conn.close()

    return deleted > 0


def get_document_by_file_hash(file_hash):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id, original_filename, indexing_status
        FROM documents
        WHERE file_hash=%s
        """,
        (file_hash,)
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row
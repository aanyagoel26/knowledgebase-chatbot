import json

from fastapi import HTTPException

from app.database.connection import get_db_connection


def create_session_if_needed(
        session_id,
        first_question,
        employee_id,
        assistant_mode):

    conn = get_db_connection()
    cursor = conn.cursor()

    if session_id is not None:
        cursor.execute(
            """
            SELECT session_id
            FROM chat_sessions
            WHERE session_id=%s
              AND employee_id=%s
              AND assistant_mode=%s
            """,
            (
                session_id,
                employee_id,
                assistant_mode
            )
        )

        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if row:
            return session_id

        raise HTTPException(
            status_code=403,
            detail="You do not have access to this chat session."
        )

    title = first_question[:60]

    cursor.execute(
        """
        INSERT INTO chat_sessions(title, employee_id, assistant_mode)
        VALUES (%s,%s,%s)
        RETURNING session_id
        """,
        (
            title,
            employee_id,
            assistant_mode
        )
    )

    new_session_id = cursor.fetchone()[0]

    conn.commit()

    cursor.close()
    conn.close()

    return new_session_id


def save_message(session_id, role, message, sources=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chat_messages(session_id, role, message, sources_json)
        VALUES (%s,%s,%s,%s)
        """,
        (
            session_id,
            role,
            message,
            json.dumps(sources) if sources else None
        )
    )

    conn.commit()

    cursor.close()
    conn.close()
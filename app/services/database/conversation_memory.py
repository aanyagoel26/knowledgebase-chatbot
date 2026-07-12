import json

from app.database.connection import get_db_connection


class DatabaseConversationMemory:
    """Loads the most recent database answer stored for a chat session.

    Memory is reconstructed from chat_messages, so no new table or migration is
    required. Only the last successful assistant payload is used as context.
    """

    def get_context(self, session_id):
        if not session_id:
            return {}

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    message,
                    answer_payload_json
                FROM chat_messages
                WHERE session_id = %s
                  AND role = 'assistant'
                  AND answer_payload_json IS NOT NULL
                ORDER BY message_id DESC
                LIMIT 1
                """,
                (session_id,)
            )

            assistant_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT message
                FROM chat_messages
                WHERE session_id = %s
                  AND role = 'user'
                ORDER BY message_id DESC
                LIMIT 2
                """,
                (session_id,)
            )

            user_rows = cursor.fetchall()

        finally:
            cursor.close()
            conn.close()

        if not assistant_row:
            return {}

        try:
            payload = json.loads(assistant_row[1]) if assistant_row[1] else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}

        # The current user message is already saved before context is loaded.
        # Therefore the second latest user message is the previous question.
        previous_question = ""
        if len(user_rows) >= 2:
            previous_question = user_rows[1][0] or ""

        return {
            "previous_question": previous_question,
            "previous_answer": assistant_row[0] or "",
            "previous_sql": payload.get("sql"),
            "previous_columns": payload.get("columns", []),
            "previous_row_count": payload.get("row_count", 0)
        }


conversation_memory = DatabaseConversationMemory()

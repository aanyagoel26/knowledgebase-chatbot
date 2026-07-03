from fastapi import APIRouter, Request

from db_server import database_assistant
from models import DBChatRequest
from auth import require_login

from app.services.intent_service import (
    detect_intent,
    generate_basic_chat_answer,
    is_basic_chat_intent
)

from app.services.session_service import (
    create_session_if_needed,
    save_message
)

router = APIRouter()


@router.post("/db-chat")
def db_chat(
        request_data: DBChatRequest,
        request: Request):

    employee = require_login(request)

    session_id = create_session_if_needed(
        request_data.session_id,
        request_data.question,
        employee["employee_id"],
        "database"
    )

    save_message(
        session_id,
        "user",
        request_data.question
    )

    intent = detect_intent(
        request_data.question,
        "database"
    )

    if is_basic_chat_intent(intent):

        answer = generate_basic_chat_answer(
            request_data.question,
            "database"
        )

        save_message(
            session_id,
            "assistant",
            answer,
            []
        )

        return {
            "session_id": session_id,
            "answer": answer,
            "sql": None,
            "columns": [],
            "rows": [],
            "execution_time": 0
        }

    result = database_assistant.answer_question(
        request_data.question
    )

    save_message(
        session_id,
        "assistant",
        result["answer"],
        []
    )

    result["session_id"] = session_id

    return result
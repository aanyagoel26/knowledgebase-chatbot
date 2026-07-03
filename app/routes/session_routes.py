import json

from fastapi import APIRouter, Request, HTTPException

from app.services.auth_service import require_login

from app.database.repository import (
    get_chat_sessions,
    user_owns_session,
    get_chat_messages
)

router = APIRouter()


@router.get("/sessions")
def get_sessions(
        request: Request,
        mode: str = "knowledge"):

    employee = require_login(request)

    rows = get_chat_sessions(
        employee["employee_id"],
        mode
    )

    sessions = []

    for row in rows:
        sessions.append(
            {
                "session_id": row[0],
                "title": row[1],
                "created_at": str(row[2])
            }
        )

    return {
        "sessions": sessions
    }


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
        session_id: int,
        request: Request):

    employee = require_login(request)

    allowed = user_owns_session(
        session_id,
        employee["employee_id"]
    )

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this chat."
        )

    rows = get_chat_messages(session_id)

    messages = []

    for row in rows:

        sources = []

        if row[3]:
            try:
                sources = json.loads(row[3])
            except Exception:
                sources = []

        messages.append(
            {
                "role": row[0],
                "message": row[1],
                "created_at": str(row[2]),
                "sources": sources
            }
        )

    return {
        "messages": messages
    }
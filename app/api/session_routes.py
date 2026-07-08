import json

from fastapi import APIRouter, HTTPException, Request

from app.database.repository import (
    delete_chat_session,
    get_chat_messages,
    get_chat_sessions,
    update_chat_session_archive,
    update_chat_session_pin,
    update_chat_session_title,
    user_owns_session
)
from app.models.request_models import (
    SessionArchiveRequest,
    SessionPinRequest,
    SessionTitleRequest
)
from app.services.auth.auth_service import require_login
from app.utils.constants import AssistantMode

router = APIRouter()


@router.get("/sessions")
def get_sessions(
        request: Request,
        mode: str = AssistantMode.KNOWLEDGE):

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
                "created_at": str(row[2]),
                "is_pinned": row[3],
                "is_archived": row[4]
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
        payload = {}

        if row[3]:
            try:
                sources = json.loads(row[3])
            except Exception:
                sources = []

        if len(row) > 4 and row[4]:
            try:
                payload = json.loads(row[4])
            except Exception:
                payload = {}

        messages.append(
            {
                "role": row[0],
                "message": row[1],
                "created_at": str(row[2]),
                "sources": sources,
                "payload": payload
            }
        )

    return {
        "messages": messages
    }


@router.patch("/sessions/{session_id}/rename")
def rename_session(
        session_id: int,
        request_data: SessionTitleRequest,
        request: Request):

    employee = require_login(request)

    title = request_data.title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="Title cannot be empty."
        )

    updated = update_chat_session_title(
        session_id,
        employee["employee_id"],
        title[:80]
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    return {
        "message": "Chat renamed successfully."
    }


@router.patch("/sessions/{session_id}/pin")
def pin_session(
        session_id: int,
        request_data: SessionPinRequest,
        request: Request):

    employee = require_login(request)

    updated = update_chat_session_pin(
        session_id,
        employee["employee_id"],
        request_data.is_pinned
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    return {
        "message": "Chat pin status updated."
    }


@router.patch("/sessions/{session_id}/archive")
def archive_session(
        session_id: int,
        request_data: SessionArchiveRequest,
        request: Request):

    employee = require_login(request)

    updated = update_chat_session_archive(
        session_id,
        employee["employee_id"],
        request_data.is_archived
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    return {
        "message": "Chat archived successfully."
    }


@router.delete("/sessions/{session_id}")
def delete_session(
        session_id: int,
        request: Request):

    employee = require_login(request)

    deleted = delete_chat_session(
        session_id,
        employee["employee_id"]
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Session not found."
        )

    return {
        "message": "Chat deleted successfully."
    }

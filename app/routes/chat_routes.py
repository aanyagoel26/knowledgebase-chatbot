from fastapi import APIRouter, Request

from app.models.request_models import ChatRequest, RetrieveRequest
from app.services.auth_service import require_login
from app.services.chat_service import (
    handle_chat_request,
    handle_retrieve_request
)

router = APIRouter()


@router.post("/retrieve")
def retrieve(
        request_data: RetrieveRequest,
        request: Request):

    require_login(request)

    return handle_retrieve_request(request_data)


@router.post("/chat")
def chat(
        request_data: ChatRequest,
        request: Request):

    employee = require_login(request)

    return handle_chat_request(
        employee,
        request_data
    )
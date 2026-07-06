from fastapi import APIRouter, Request
from app.models.request_models import RetrieveRequest, ChatRequest
from app.services.auth_service import require_login
from app.services.intent_service import (
    detect_intent,
    generate_basic_chat_answer,
    is_basic_chat_intent,
    is_summary_intent
)
from app.services.retrieval_service import (
    retrieve_relevant_chunks,
    retrieve_document_summary_chunks
)
from app.services.answer_service import generate_answer
from app.services.session_service import (
    create_session_if_needed,
    save_message
)
from app.utils.constants import (
    AssistantMode,
    SearchScope,
    DefaultMessage
)
from app.utils.constants import (
    AssistantMode,
    SearchScope,
    DefaultMessage,
    MessageRole
)
router = APIRouter()


@router.post("/retrieve")
def retrieve(
        request_data: RetrieveRequest,
        request: Request):

    require_login(request)

    intent = detect_intent(
        request_data.question,
        AssistantMode.KNOWLEDGE
    )

    if request_data.document_ids and is_summary_intent(intent):
        chunks = retrieve_document_summary_chunks(
            request_data.document_ids
        )
    else:
        chunks = retrieve_relevant_chunks(
            request_data.question,
            request_data.document_ids
        )

    return {
        "question": request_data.question,
        "document_ids": request_data.document_ids,
        "search_scope": (
            SearchScope.SELECTED_DOCUMENTS
            if request_data.document_ids
            else SearchScope.ALL_READY_DOCUMENTS
        ),
        "chunks": [
            {
                "rank": index + 1,
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "chunk_number": chunk["chunk_number"],
                "retrieval_type": chunk["retrieval_type"],
                "final_score": round(chunk["final_score"], 4),
                "keyword_hits": chunk["keyword_hits"],
                "from_vector": chunk["from_vector"],
                "from_keyword": chunk["from_keyword"],
                "content_preview": chunk["content"][:700]
            }
            for index, chunk in enumerate(chunks)
        ]
    }


@router.post("/chat")
def chat(
        request_data: ChatRequest,
        request: Request):

    employee = require_login(request)

    session_id = create_session_if_needed(
        request_data.session_id,
        request_data.question,
        employee["employee_id"],
        AssistantMode.KNOWLEDGE
    )

    save_message(
        session_id,
        MessageRole.USER,
        request_data.question
    )

    intent = detect_intent(
        request_data.question,
        AssistantMode.KNOWLEDGE
    )

    if is_basic_chat_intent(intent):

        answer = generate_basic_chat_answer(
            request_data.question,
            AssistantMode.KNOWLEDGE
        )

        save_message(
            session_id,
            MessageRole.ASSISTANT,
            answer,
            []
        )

        return {
            "session_id": session_id,
            "answer": answer,
            "search_scope": SearchScope.BASIC_CHAT,
            "document_ids": request_data.document_ids,
            "sources": []
        }

    if request_data.document_ids and is_summary_intent(intent):
        chunks = retrieve_document_summary_chunks(
            request_data.document_ids
        )
    else:
        chunks = retrieve_relevant_chunks(
            request_data.question,
            request_data.document_ids
        )

    if not chunks:

        answer = DefaultMessage.NO_RELIABLE_INFORMATION

        save_message(
            session_id,
            MessageRole.ASSISTANT,
            answer,
            []
        )

        return {
            "session_id": session_id,
            "answer": answer,
            "search_scope": (
                SearchScope.SELECTED_DOCUMENTS
                if request_data.document_ids
                else SearchScope.ALL_READY_DOCUMENTS
            ),
            "document_ids": request_data.document_ids,
            "sources": []
        }

    answer = generate_answer(
        request_data.question,
        chunks
    )

    unique_sources = {}

    for chunk in chunks:
        unique_sources[chunk["document_id"]] = {
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "download_url": (
                f"/download-document/{chunk['document_id']}"
            )
        }

    sources_list = list(unique_sources.values())

    save_message(
        session_id,
        MessageRole.ASSISTANT,
        answer,
        sources_list
    )

    return {
        "session_id": session_id,
        "answer": answer,
        "search_scope": (
            SearchScope.SELECTED_DOCUMENTS
            if request_data.document_ids
            else SearchScope.ALL_READY_DOCUMENTS
        ),
        "document_ids": request_data.document_ids,
        "sources": sources_list
    }
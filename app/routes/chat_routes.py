from fastapi import APIRouter, Request

from models import RetrieveRequest, ChatRequest

from auth import require_login

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

router = APIRouter()


@router.post("/retrieve")
def retrieve(
        request_data: RetrieveRequest,
        request: Request):

    require_login(request)

    intent = detect_intent(
        request_data.question,
        "knowledge"
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
            "selected_documents"
            if request_data.document_ids
            else "all_ready_documents"
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
        "knowledge"
    )

    save_message(
        session_id,
        "user",
        request_data.question
    )

    intent = detect_intent(
        request_data.question,
        "knowledge"
    )

    if is_basic_chat_intent(intent):

        answer = generate_basic_chat_answer(
            request_data.question,
            "knowledge"
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
            "search_scope": "basic_chat",
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

        answer = (
            "I could not find reliable information for this question "
            "in the indexed documents. Please try selecting the correct document "
            "or rephrasing the question."
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
            "search_scope": (
                "selected_documents"
                if request_data.document_ids
                else "all_ready_documents"
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
        "assistant",
        answer,
        sources_list
    )

    return {
        "session_id": session_id,
        "answer": answer,
        "search_scope": (
            "selected_documents"
            if request_data.document_ids
            else "all_ready_documents"
        ),
        "document_ids": request_data.document_ids,
        "sources": sources_list
    }
class DocumentStatus:
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class AssistantMode:
    KNOWLEDGE = "knowledge"
    DATABASE = "database"


class SourceType:
    KNOWLEDGE_BASE = "knowledge_base"
    UPLOADED = "uploaded"


class SearchScope:
    BASIC_CHAT = "basic_chat"
    SELECTED_DOCUMENTS = "selected_documents"
    ALL_READY_DOCUMENTS = "all_ready_documents"


class DefaultMessage:
    NO_RELIABLE_INFORMATION = (
        "I could not find reliable information for this question "
        "in the indexed documents. Please try selecting the correct document "
        "or rephrasing the question."
    )

class MessageRole:
    USER = "user"
    ASSISTANT = "assistant"
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
import psycopg2
import requests
import os
import shutil
import hashlib
import re
import csv
from datetime import datetime
import fitz
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

app = FastAPI()

DB_HOST = "localhost"
DB_NAME = "kb_chatbot"
DB_USER = "postgres"
DB_PASSWORD = "Aanya2612"

CHAT_MODEL = "qwen2.5:7b"
EMBEDDING_MODEL = "nomic-embed-text"

KNOWLEDGE_BASE_FOLDER = "knowledge_base"
UPLOAD_FOLDER = "uploads"
UI_FILE = "kb_chat.html"

MAX_CHUNK_SIZE = 600
CHUNK_OVERLAP = 100

VECTOR_TOP_K = 35
KEYWORD_TOP_K = 35
FINAL_TOP_K = 8

NEIGHBOR_WINDOW = 2
MAX_CONTEXT_CHUNKS = 22


class RetrieveRequest(BaseModel):
    question: str
    document_ids: list[int] = []


class ChatRequest(BaseModel):
    question: str
    session_id: int | None = None
    document_ids: list[int] = []


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def ensure_folders():
    os.makedirs(KNOWLEDGE_BASE_FOLDER, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs("logs", exist_ok=True)


def calculate_file_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(block)

    return sha256.hexdigest()


def get_file_metadata(file_path):
    stat = os.stat(file_path)

    return {
        "file_size": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime)
    }


def clean_text(text):
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    stopwords = {
        "the", "is", "are", "was", "were", "a", "an", "of", "for", "to",
        "in", "on", "and", "or", "with", "from", "by", "as", "at", "this",
        "that", "it", "be", "can", "what", "which", "who", "when", "where",
        "how", "tell", "me", "about", "give", "list", "explain", "show",
        "please", "kindly", "all", "any"
    }

    return [word for word in text.split() if word not in stopwords]


def extract_pdf(file_path):
    document = fitz.open(file_path)
    text = ""

    for page_number, page in enumerate(document, start=1):
        text += f"\n\nPage {page_number}\n{page.get_text()}"

    document.close()
    return text


def extract_docx(file_path):
    doc = Document(file_path)
    text = ""

    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text += paragraph.text.strip() + "\n"

    for table in doc.tables:
        for row in table.rows:
            row_values = []

            for cell in row.cells:
                if cell.text.strip():
                    row_values.append(cell.text.strip())

            if row_values:
                text += " | ".join(row_values) + "\n"

    return text


def extract_xlsx(file_path):
    workbook = load_workbook(file_path, data_only=True)
    text = ""

    for sheet in workbook.worksheets:
        text += f"\n\nSheet: {sheet.title}\n"

        for row in sheet.iter_rows(values_only=True):
            values = []

            for cell in row:
                if cell is not None:
                    values.append(str(cell))

            if values:
                text += " | ".join(values) + "\n"

    return text


def extract_csv(file_path):
    text = ""

    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
        reader = csv.reader(file)

        for row in reader:
            text += " | ".join(row) + "\n"

    return text


def extract_pptx(file_path):
    presentation = Presentation(file_path)
    text = ""

    for slide_number, slide in enumerate(presentation.slides, start=1):
        text += f"\n\nSlide {slide_number}\n"

        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                text += shape.text.strip() + "\n"

    return text


def extract_text_file(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
        return file.read()


def extract_text(file_path):
    extension = file_path.lower().split(".")[-1]

    if extension == "pdf":
        return extract_pdf(file_path)

    if extension == "docx":
        return extract_docx(file_path)

    if extension == "xlsx":
        return extract_xlsx(file_path)

    if extension == "csv":
        return extract_csv(file_path)

    if extension == "pptx":
        return extract_pptx(file_path)

    if extension in ["txt", "md"]:
        return extract_text_file(file_path)

    raise ValueError("Unsupported file type: " + extension)


def is_supported_file(file_path):
    supported_extensions = ["pdf", "docx", "xlsx", "csv", "pptx", "txt", "md"]
    extension = file_path.lower().split(".")[-1]
    return extension in supported_extensions


def recursive_split(text, separators):
    if len(text) <= MAX_CHUNK_SIZE:
        return [text]

    if not separators:
        return [
            text[i:i + MAX_CHUNK_SIZE]
            for i in range(0, len(text), MAX_CHUNK_SIZE)
        ]

    separator = separators[0]
    parts = text.split(separator)

    if len(parts) == 1:
        return recursive_split(text, separators[1:])

    chunks = []
    current = ""

    for part in parts:
        part = part.strip()

        if not part:
            continue

        candidate = current + separator + part if current else part

        if len(candidate) <= MAX_CHUNK_SIZE:
            current = candidate
        else:
            if current:
                chunks.extend(recursive_split(current, separators[1:]))

            current = part

    if current:
        chunks.extend(recursive_split(current, separators[1:]))

    return chunks


def add_overlap(chunks):
    final_chunks = []

    for chunk in chunks:
        chunk = chunk.strip()

        if not chunk:
            continue

        if not final_chunks:
            final_chunks.append(chunk)
        else:
            previous = final_chunks[-1]
            overlap_text = previous[-CHUNK_OVERLAP:]
            combined = overlap_text + "\n" + chunk

            if len(combined) <= MAX_CHUNK_SIZE + CHUNK_OVERLAP:
                final_chunks.append(combined.strip())
            else:
                final_chunks.append(chunk)

    return final_chunks


def split_text_into_chunks(text):
    text = clean_text(text)

    separators = [
        "\n\n",
        "\n",
        ". ",
        "; ",
        ", ",
        " "
    ]

    raw_chunks = recursive_split(text, separators)

    safe_chunks = []

    for chunk in raw_chunks:
        if len(chunk) <= MAX_CHUNK_SIZE:
            safe_chunks.append(chunk)
        else:
            for i in range(0, len(chunk), MAX_CHUNK_SIZE):
                safe_chunks.append(chunk[i:i + MAX_CHUNK_SIZE])

    final_chunks = add_overlap(safe_chunks)

    return [
        chunk.strip()
        for chunk in final_chunks
        if len(chunk.strip()) > 30
    ]


def generate_embedding(text):
    print("Generating embedding | length:", len(text))

    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={
            "model": EMBEDDING_MODEL,
            "prompt": text
        },
        timeout=120
    )

    if response.status_code != 200:
        print("Embedding failed")
        print(response.text)
        raise Exception("Embedding API failed")

    return response.json()["embedding"]


def index_file(file_path, source_type, force_reindex=False):
    absolute_path = os.path.abspath(file_path)
    original_filename = os.path.basename(file_path)
    metadata = get_file_metadata(file_path)

    print("\n" + "=" * 80)
    print("INDEXING FILE")
    print("=" * 80)
    print("Filename:", original_filename)
    print("Path:", absolute_path)
    print("Source:", source_type)
    print("Force reindex:", force_reindex)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id, file_hash, file_size, last_modified, version
        FROM documents
        WHERE file_path = %s
        """,
        (absolute_path,)
    )

    existing_by_path = cursor.fetchone()

    if existing_by_path:
        document_id, old_hash, old_size, old_modified, old_version = existing_by_path

        if not force_reindex:
            if old_size == metadata["file_size"] and old_modified == metadata["last_modified"]:
                cursor.close()
                conn.close()

                print("Status: unchanged file path. Skipped.")

                return {
                    "filename": original_filename,
                    "status": "skipped_unchanged",
                    "message": "File already indexed and unchanged."
                }

        new_hash = calculate_file_hash(file_path)

        if not force_reindex:
            if new_hash == old_hash:
                cursor.execute(
                    """
                    UPDATE documents
                    SET file_size = %s,
                        last_modified = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE document_id = %s
                    """,
                    (
                        metadata["file_size"],
                        metadata["last_modified"],
                        document_id
                    )
                )

                conn.commit()
                cursor.close()
                conn.close()

                print("Status: metadata changed but content same. Skipped re-index.")

                return {
                    "filename": original_filename,
                    "status": "skipped_same_hash",
                    "message": "Metadata changed but content is same."
                }

        print("Status: re-indexing existing document.")
        print("Deleting old chunks for document_id:", document_id)

        cursor.execute(
            """
            DELETE FROM document_chunks
            WHERE document_id = %s
            """,
            (document_id,)
        )

        extracted_text = extract_text(file_path)
        chunks = split_text_into_chunks(extracted_text)

        print("Characters extracted:", len(extracted_text))
        print("New chunks created:", len(chunks))

        for index, chunk in enumerate(chunks, start=1):
            print(f"Embedding updated chunk {index}/{len(chunks)}")
            embedding = generate_embedding(chunk)

            cursor.execute(
                """
                INSERT INTO document_chunks
                (document_id, chunk_number, content, embedding, token_count)
                VALUES (%s, %s, %s, %s::vector, %s)
                """,
                (
                    document_id,
                    index,
                    chunk,
                    str(embedding),
                    len(tokenize(chunk))
                )
            )

        cursor.execute(
            """
            UPDATE documents
            SET file_hash = %s,
                file_size = %s,
                last_modified = %s,
                version = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE document_id = %s
            """,
            (
                new_hash,
                metadata["file_size"],
                metadata["last_modified"],
                old_version + 1,
                document_id
            )
        )

        conn.commit()
        cursor.close()
        conn.close()

        print("Status: existing document re-indexed.")

        return {
            "filename": original_filename,
            "status": "reindexed",
            "chunks": len(chunks),
            "version": old_version + 1
        }

    file_hash = calculate_file_hash(file_path)

    cursor.execute(
        """
        SELECT document_id
        FROM documents
        WHERE file_hash = %s
        """,
        (file_hash,)
    )

    existing_by_hash = cursor.fetchone()

    if existing_by_hash and not force_reindex:
        cursor.close()
        conn.close()

        print("Status: duplicate content found. Skipped chunks and embeddings.")

        return {
            "filename": original_filename,
            "status": "skipped_duplicate",
            "message": "Same content already indexed."
        }

    extracted_text = extract_text(file_path)
    chunks = split_text_into_chunks(extracted_text)

    print("Status: new document.")
    print("Characters extracted:", len(extracted_text))
    print("Chunks created:", len(chunks))

    cursor.execute(
        """
        INSERT INTO documents
        (original_filename, file_path, file_hash, file_size, last_modified, source_type)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING document_id
        """,
        (
            original_filename,
            absolute_path,
            file_hash,
            metadata["file_size"],
            metadata["last_modified"],
            source_type
        )
    )

    document_id = cursor.fetchone()[0]

    for index, chunk in enumerate(chunks, start=1):
        print(f"Embedding chunk {index}/{len(chunks)}")
        embedding = generate_embedding(chunk)

        cursor.execute(
            """
            INSERT INTO document_chunks
            (document_id, chunk_number, content, embedding, token_count)
            VALUES (%s, %s, %s, %s::vector, %s)
            """,
            (
                document_id,
                index,
                chunk,
                str(embedding),
                len(tokenize(chunk))
            )
        )

    conn.commit()
    cursor.close()
    conn.close()

    print("Status: new document indexed successfully.")

    return {
        "filename": original_filename,
        "status": "indexed_new",
        "document_id": document_id,
        "chunks": len(chunks)
    }


def scan_knowledge_base(force_reindex=False):
    ensure_folders()

    print("\n" + "=" * 80)
    print("SCANNING KNOWLEDGE BASE")
    print("=" * 80)
    print("Force reindex:", force_reindex)

    results = []

    for root, dirs, files in os.walk(KNOWLEDGE_BASE_FOLDER):
        for filename in files:
            file_path = os.path.join(root, filename)

            if is_supported_file(file_path):
                result = index_file(file_path, "knowledge_base", force_reindex)
                results.append(result)
            else:
                results.append({
                    "filename": filename,
                    "status": "unsupported"
                })

    return results


def build_document_filter(document_ids):
    if not document_ids:
        return "", []

    placeholders = ",".join(["%s"] * len(document_ids))
    return f" AND c.document_id IN ({placeholders}) ", document_ids


def get_vector_rows(cursor, question, document_ids=None):
    question_embedding = generate_embedding(question)
    document_ids = document_ids or []

    filter_sql, filter_params = build_document_filter(document_ids)

    query = f"""
        SELECT 
            c.chunk_id,
            c.document_id,
            d.original_filename,
            c.chunk_number,
            c.content,
            c.embedding <=> %s::vector AS distance
        FROM document_chunks c
        JOIN documents d
        ON c.document_id = d.document_id
        WHERE 1=1
        {filter_sql}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """

    params = [str(question_embedding)] + filter_params + [str(question_embedding), VECTOR_TOP_K]

    cursor.execute(query, params)

    return cursor.fetchall()


def get_keyword_rows(cursor, question, document_ids=None):
    keywords = tokenize(question)
    document_ids = document_ids or []

    if not keywords:
        return []

    keyword_conditions = []
    params = []

    for keyword in keywords:
        keyword_conditions.append("c.content ILIKE %s")
        params.append("%" + keyword + "%")

    document_filter_sql, document_filter_params = build_document_filter(document_ids)

    query = f"""
        SELECT 
            c.chunk_id,
            c.document_id,
            d.original_filename,
            c.chunk_number,
            c.content,
            1.0 AS distance
        FROM document_chunks c
        JOIN documents d
        ON c.document_id = d.document_id
        WHERE ({" OR ".join(keyword_conditions)})
        {document_filter_sql}
        LIMIT %s
    """

    params = params + document_filter_params + [KEYWORD_TOP_K]

    cursor.execute(query, params)

    return cursor.fetchall()


def merge_retrieval_results(vector_rows, keyword_rows):
    merged = {}

    for row in vector_rows:
        chunk_id = row[0]

        merged[chunk_id] = {
            "chunk_id": row[0],
            "document_id": row[1],
            "filename": row[2],
            "chunk_number": row[3],
            "content": row[4],
            "vector_distance": float(row[5]),
            "from_vector": True,
            "from_keyword": False,
            "retrieval_type": "direct"
        }

    for row in keyword_rows:
        chunk_id = row[0]

        if chunk_id in merged:
            merged[chunk_id]["from_keyword"] = True
        else:
            merged[chunk_id] = {
                "chunk_id": row[0],
                "document_id": row[1],
                "filename": row[2],
                "chunk_number": row[3],
                "content": row[4],
                "vector_distance": float(row[5]),
                "from_vector": False,
                "from_keyword": True,
                "retrieval_type": "direct"
            }

    return list(merged.values())


def rerank_chunks(chunks, question):
    question_words = set(tokenize(question))
    reranked = []

    for chunk in chunks:
        content_words = set(tokenize(chunk["content"]))

        keyword_hits = len(question_words.intersection(content_words))
        vector_score = 1 / (1 + chunk["vector_distance"])

        source_bonus = 0

        if chunk["from_vector"]:
            source_bonus += 0.5

        if chunk["from_keyword"]:
            source_bonus += 1.0

        exact_phrase_bonus = 0

        if question.lower().strip() in chunk["content"].lower():
            exact_phrase_bonus = 3.0

        final_score = keyword_hits + vector_score + source_bonus + exact_phrase_bonus

        chunk["keyword_hits"] = keyword_hits
        chunk["vector_score"] = vector_score
        chunk["final_score"] = final_score

        reranked.append(chunk)

    reranked.sort(key=lambda item: item["final_score"], reverse=True)

    return reranked


def fetch_neighbor_chunks(cursor, ranked_chunks):
    neighbor_map = {}

    for chunk in ranked_chunks:
        document_id = chunk["document_id"]
        center_chunk_number = chunk["chunk_number"]

        start_chunk = max(1, center_chunk_number - NEIGHBOR_WINDOW)
        end_chunk = center_chunk_number + NEIGHBOR_WINDOW

        cursor.execute(
            """
            SELECT 
                c.chunk_id,
                c.document_id,
                d.original_filename,
                c.chunk_number,
                c.content
            FROM document_chunks c
            JOIN documents d
            ON c.document_id = d.document_id
            WHERE c.document_id = %s
              AND c.chunk_number BETWEEN %s AND %s
            ORDER BY c.chunk_number ASC
            """,
            (
                document_id,
                start_chunk,
                end_chunk
            )
        )

        rows = cursor.fetchall()

        for row in rows:
            chunk_id = row[0]

            if chunk_id not in neighbor_map:
                neighbor_map[chunk_id] = {
                    "chunk_id": row[0],
                    "document_id": row[1],
                    "filename": row[2],
                    "chunk_number": row[3],
                    "content": row[4],
                    "vector_distance": chunk["vector_distance"],
                    "from_vector": chunk["from_vector"],
                    "from_keyword": chunk["from_keyword"],
                    "retrieval_type": "neighbor_expansion",
                    "keyword_hits": chunk.get("keyword_hits", 0),
                    "vector_score": chunk.get("vector_score", 0),
                    "final_score": chunk.get("final_score", 0)
                }

    return list(neighbor_map.values())


def build_context_chunks(cursor, ranked_chunks):
    direct_chunks = ranked_chunks[:FINAL_TOP_K]
    neighbor_chunks = fetch_neighbor_chunks(cursor, direct_chunks)

    combined = {}

    for chunk in direct_chunks + neighbor_chunks:
        combined[chunk["chunk_id"]] = chunk

    combined_chunks = list(combined.values())

    combined_chunks.sort(
        key=lambda item: (
            item["document_id"],
            item["chunk_number"]
        )
    )

    return combined_chunks[:MAX_CONTEXT_CHUNKS]


def retrieve_relevant_chunks(question, document_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    document_ids = document_ids or []

    print("\n" + "=" * 80)
    print("RETRIEVAL STARTED")
    print("=" * 80)
    print("Question:", question)
    print("Document filter:", document_ids if document_ids else "ALL DOCUMENTS")

    vector_rows = get_vector_rows(cursor, question, document_ids)
    keyword_rows = get_keyword_rows(cursor, question, document_ids)

    merged_chunks = merge_retrieval_results(vector_rows, keyword_rows)
    ranked_chunks = rerank_chunks(merged_chunks, question)

    final_chunks = build_context_chunks(cursor, ranked_chunks)

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("FINAL CONTEXT CHUNKS")
    print("=" * 80)

    for index, chunk in enumerate(final_chunks, start=1):
        print("Context Rank:", index)
        print("Document ID:", chunk["document_id"])
        print("File:", chunk["filename"])
        print("Chunk:", chunk["chunk_number"])
        print("Retrieval Type:", chunk["retrieval_type"])
        print("Score:", round(chunk["final_score"], 4))
        print("Preview:", chunk["content"][:300])
        print("-" * 80)

    return final_chunks


def create_session_if_needed(session_id, first_question):
    conn = get_db_connection()
    cursor = conn.cursor()

    if session_id is not None:
        cursor.close()
        conn.close()
        return session_id

    title = first_question[:60]

    cursor.execute(
        """
        INSERT INTO chat_sessions(title)
        VALUES (%s)
        RETURNING session_id
        """,
        (title,)
    )

    new_session_id = cursor.fetchone()[0]

    conn.commit()
    cursor.close()
    conn.close()

    return new_session_id


def save_message(session_id, role, message):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chat_messages(session_id, role, message)
        VALUES (%s, %s, %s)
        """,
        (
            session_id,
            role,
            message
        )
    )

    conn.commit()
    cursor.close()
    conn.close()


def generate_answer(question, chunks):
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"Source {index}\n"
            f"Document ID: {chunk['document_id']}\n"
            f"File: {chunk['filename']}\n"
            f"Chunk: {chunk['chunk_number']}\n"
            f"Content:\n{chunk['content']}"
        )

    context = "\n\n-------------------------\n\n".join(context_parts)

    system_prompt = """
You are a strict knowledge-base assistant.

Use only the given knowledge base content.

Rules:
- Answer only from the given content.
- Do not use outside knowledge.
- Do not guess missing facts.
- Do not invent names, numbers, dates, policies, rules, or facts.
- If multiple related points are present, include all relevant points.
- If the exact answer is spread across multiple chunks, combine them into one complete answer.
- If the question is vague, summarize the most relevant information from the retrieved content.
- If the user asks "this pdf" or "this document", answer only from the selected document content that was provided.
- Keep the answer clear, professional, and structured.
- Do not say "based on context" or "retrieved chunks".
"""

    user_prompt = f"""
Knowledge base content:
{context}

User question:
{question}

Give the final answer only.
"""

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "stream": False
        },
        timeout=180
    )

    if response.status_code != 200:
        print(response.text)
        raise Exception("Chat model failed")

    return response.json()["message"]["content"].strip()


@app.on_event("startup")
def startup_event():
    ensure_folders()
    print("\nKB Chatbot backend started.")
    print("Knowledge base folder:", os.path.abspath(KNOWLEDGE_BASE_FOLDER))
    print("Uploads folder:", os.path.abspath(UPLOAD_FOLDER))


@app.get("/")
def home():
    return FileResponse(UI_FILE)


@app.get("/health")
def health_check():
    return {
        "status": "Backend is running"
    }


@app.get("/db-check")
def db_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
            """
        )

        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "database": "connected",
            "tables": [row[0] for row in rows]
        }

    except Exception as error:
        return {
            "database": "connection failed",
            "error": str(error)
        }


@app.post("/index-knowledge-base")
def index_knowledge_base(force: bool = False):
    results = scan_knowledge_base(force)

    return {
        "message": "Knowledge base indexing completed.",
        "force_reindex": force,
        "results": results
    }


@app.post("/upload")
async def upload_documents(request: Request):
    ensure_folders()

    form = await request.form()
    uploaded_files = form.getlist("files")

    results = []

    if not uploaded_files:
        return {
            "message": "No files received.",
            "results": []
        }

    for file in uploaded_files:
        safe_filename = os.path.basename(file.filename)
        save_path = os.path.join(UPLOAD_FOLDER, safe_filename)

        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if not is_supported_file(save_path):
            results.append({
                "filename": safe_filename,
                "status": "unsupported"
            })
            continue

        result = index_file(save_path, "user_upload", False)
        results.append(result)

    return {
        "message": "Upload processing completed.",
        "results": results
    }


@app.get("/documents")
def list_documents():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 
            d.document_id,
            d.original_filename,
            d.source_type,
            d.version,
            COUNT(c.chunk_id) AS chunks,
            d.indexed_at,
            d.updated_at
        FROM documents d
        LEFT JOIN document_chunks c
        ON d.document_id = c.document_id
        GROUP BY d.document_id
        ORDER BY d.updated_at DESC;
        """
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "documents": [
            {
                "document_id": row[0],
                "filename": row[1],
                "source_type": row[2],
                "version": row[3],
                "chunks": row[4],
                "indexed_at": str(row[5]),
                "updated_at": str(row[6])
            }
            for row in rows
        ]
    }


@app.post("/retrieve")
def retrieve(request: RetrieveRequest):
    chunks = retrieve_relevant_chunks(
        request.question,
        request.document_ids
    )

    return {
        "question": request.question,
        "document_ids": request.document_ids,
        "search_scope": "selected_documents" if request.document_ids else "all_documents",
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


@app.post("/chat")
def chat(request: ChatRequest):
    session_id = create_session_if_needed(
        request.session_id,
        request.question
    )

    save_message(session_id, "user", request.question)

    chunks = retrieve_relevant_chunks(
        request.question,
        request.document_ids
    )

    if not chunks:
        answer = "No relevant knowledge base content was found for the selected document scope."
        save_message(session_id, "assistant", answer)

        return {
            "session_id": session_id,
            "answer": answer,
            "sources": []
        }

    answer = generate_answer(request.question, chunks)

    save_message(session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "answer": answer,
        "search_scope": "selected_documents" if request.document_ids else "all_documents",
        "document_ids": request.document_ids,
        "sources": [
            {
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "chunk_number": chunk["chunk_number"],
                "retrieval_type": chunk["retrieval_type"],
                "score": round(chunk["final_score"], 4)
            }
            for chunk in chunks
        ]
    }


@app.get("/sessions")
def get_sessions():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT session_id, title, created_at
        FROM chat_sessions
        ORDER BY created_at DESC;
        """
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "sessions": [
            {
                "session_id": row[0],
                "title": row[1],
                "created_at": str(row[2])
            }
            for row in rows
        ]
    }


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, message, created_at
        FROM chat_messages
        WHERE session_id = %s
        ORDER BY created_at ASC;
        """,
        (session_id,)
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "messages": [
            {
                "role": row[0],
                "message": row[1],
                "created_at": str(row[2])
            }
            for row in rows
        ]
    }
from app.database.connection import get_db_connection

from app.config.settings import (
    PER_DOCUMENT_VECTOR_TOP_K,
    PER_DOCUMENT_KEYWORD_TOP_K,
    PER_DOCUMENT_DIRECT_TOP_K,
    PER_DOCUMENT_CONTEXT_LIMIT,
    NEIGHBOR_WINDOW,
    MAX_CONTEXT_CHUNKS_TOTAL
)

from app.services.embedding_service import generate_embedding
from app.services.document_service import tokenize


def get_ready_document_ids():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT document_id
        FROM documents
        WHERE indexing_status='ready'
        ORDER BY updated_at DESC
        """
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return [row[0] for row in rows]


def build_document_filter(document_ids):
    if not document_ids:
        return "", []

    placeholders = ",".join(["%s"] * len(document_ids))

    return f" AND c.document_id IN ({placeholders}) ", document_ids


def get_vector_rows(
        cursor,
        question,
        document_ids=None,
        limit=PER_DOCUMENT_VECTOR_TOP_K):

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
        ON c.document_id=d.document_id
        WHERE d.indexing_status='ready'
        {filter_sql}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """

    params = (
        [str(question_embedding)]
        + filter_params
        + [str(question_embedding), limit]
    )

    cursor.execute(query, params)

    return cursor.fetchall()


def get_keyword_rows(
        cursor,
        question,
        document_ids=None,
        limit=PER_DOCUMENT_KEYWORD_TOP_K):

    keywords = tokenize(question)
    document_ids = document_ids or []

    if not keywords:
        return []

    keyword_conditions = []
    params = []

    for keyword in keywords:
        keyword_conditions.append("c.content ILIKE %s")
        params.append("%" + keyword + "%")

    document_filter_sql, document_filter_params = build_document_filter(
        document_ids
    )

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
        ON c.document_id=d.document_id
        WHERE d.indexing_status='ready'
        AND ({" OR ".join(keyword_conditions)})
        {document_filter_sql}
        LIMIT %s
    """

    params = params + document_filter_params + [limit]

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
    question_text = question.lower().strip()

    reranked = []

    for chunk in chunks:
        content_lower = chunk["content"].lower()
        filename_lower = chunk["filename"].lower()
        content_words = set(tokenize(chunk["content"]))

        keyword_hits = len(question_words.intersection(content_words))
        keyword_coverage = keyword_hits / max(1, len(question_words))
        vector_score = 1 / (1 + chunk["vector_distance"])

        filename_hits = 0
        for word in question_words:
            if word in filename_lower:
                filename_hits += 1

        filename_bonus = filename_hits * 6.0

        exact_phrase_bonus = 0
        if question_text and question_text in content_lower:
            exact_phrase_bonus += 4.0

        content_title_bonus = 0
        for word in question_words:
            if word in content_lower[:300]:
                content_title_bonus += 2.0

        source_bonus = 0
        if chunk["from_vector"]:
            source_bonus += 0.4
        if chunk["from_keyword"]:
            source_bonus += 0.8

        penalty = 0
        if keyword_coverage == 0 and filename_hits == 0:
            penalty += 4.0

        final_score = (
            keyword_hits
            + keyword_coverage
            + vector_score
            + source_bonus
            + filename_bonus
            + exact_phrase_bonus
            + content_title_bonus
            - penalty
        )

        chunk["keyword_hits"] = keyword_hits
        chunk["keyword_coverage"] = keyword_coverage
        chunk["filename_hits"] = filename_hits
        chunk["vector_score"] = vector_score
        chunk["final_score"] = final_score

        reranked.append(chunk)

    reranked = [
        chunk for chunk in reranked
        if chunk["final_score"] >= 2.5
    ]

    reranked.sort(
        key=lambda item: item["final_score"],
        reverse=True
    )

    return reranked


def fetch_neighbor_chunks(cursor, ranked_chunks):
    neighbor_map = {}

    for chunk in ranked_chunks:
        document_id = chunk["document_id"]
        center_chunk_number = chunk["chunk_number"]

        start_chunk = max(
            1,
            center_chunk_number - NEIGHBOR_WINDOW
        )

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
            ON c.document_id=d.document_id
            WHERE c.document_id=%s
              AND c.chunk_number BETWEEN %s AND %s
              AND d.indexing_status='ready'
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


def build_context_chunks_for_document(
        cursor,
        ranked_chunks,
        dynamic_limit):

    direct_chunks = ranked_chunks[:PER_DOCUMENT_DIRECT_TOP_K]

    neighbor_chunks = fetch_neighbor_chunks(
        cursor,
        direct_chunks
    )

    combined = {}

    for chunk in direct_chunks + neighbor_chunks:
        combined[chunk["chunk_id"]] = chunk

    combined_chunks = list(combined.values())

    combined_chunks.sort(
        key=lambda item: item["chunk_number"]
    )

    return combined_chunks[:dynamic_limit]


def retrieve_relevant_chunks(question, document_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    requested_document_ids = document_ids or []

    if requested_document_ids:
        target_document_ids = requested_document_ids
    else:
        target_document_ids = get_ready_document_ids()

    if not target_document_ids:
        cursor.close()
        conn.close()
        return []

    per_document_limit = max(
        3,
        min(
            PER_DOCUMENT_CONTEXT_LIMIT,
            MAX_CONTEXT_CHUNKS_TOTAL
            // max(1, len(target_document_ids))
        )
    )

    final_chunks = []

    for document_id in target_document_ids:
        vector_rows = get_vector_rows(
            cursor,
            question,
            [document_id],
            PER_DOCUMENT_VECTOR_TOP_K
        )

        keyword_rows = get_keyword_rows(
            cursor,
            question,
            [document_id],
            PER_DOCUMENT_KEYWORD_TOP_K
        )

        merged_chunks = merge_retrieval_results(
            vector_rows,
            keyword_rows
        )

        ranked_chunks = rerank_chunks(
            merged_chunks,
            question
        )

        if not ranked_chunks:
            continue

        document_context_chunks = build_context_chunks_for_document(
            cursor,
            ranked_chunks,
            per_document_limit
        )

        final_chunks.extend(document_context_chunks)

    cursor.close()
    conn.close()

    final_chunks.sort(
        key=lambda item: item.get("final_score", 0),
        reverse=True
    )

    return final_chunks[:MAX_CONTEXT_CHUNKS_TOTAL]


def retrieve_document_summary_chunks(document_ids):
    if not document_ids:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()

    chunks = []

    per_document_limit = max(
        2,
        MAX_CONTEXT_CHUNKS_TOTAL // max(1, len(document_ids))
    )

    for document_id in document_ids:
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
              AND d.indexing_status = 'ready'
              AND c.content IS NOT NULL
              AND LENGTH(TRIM(c.content)) > 30
            ORDER BY c.chunk_number ASC
            LIMIT %s
            """,
            (
                document_id,
                per_document_limit
            )
        )

        rows = cursor.fetchall()

        for row in rows:
            chunks.append(
                {
                    "chunk_id": row[0],
                    "document_id": row[1],
                    "filename": row[2],
                    "chunk_number": row[3],
                    "content": row[4],
                    "vector_distance": 0,
                    "from_vector": False,
                    "from_keyword": False,
                    "retrieval_type": "document_summary",
                    "keyword_hits": 0,
                    "vector_score": 0,
                    "final_score": 10
                }
            )

    cursor.close()
    conn.close()

    return chunks
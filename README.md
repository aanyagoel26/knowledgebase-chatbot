# KnowledgeBase Chatbot 
                                   ┌──────────────────────────────┐
                                   │          START               │
                                   │  User opens KB Chatbot UI    │
                                   └──────────────┬───────────────┘
                                                  │
                                                  ▼
                                   ┌───────────────────────────────┐
                                   │      FastAPI Server Starts    │
                                   │ uvicorn kb_server:app --reload│
                                   └──────────────┬────────────────┘
                                                  │
                                                  ▼
                                   ┌──────────────────────────────┐
                                   │        startup_event()       │
                                   └──────────────┬───────────────┘
                                                  │
                       ┌──────────────────────────┴──────────────────────────┐
                       ▼                                                     ▼
        ┌──────────────────────────────┐                      ┌──────────────────────────────┐
        │      ensure_folders()        │                      │   ensure_schema_updates()    │
        │ Creates knowledge_base folder│                      │ Adds production DB columns   │
        └──────────────┬───────────────┘                      └──────────────┬───────────────┘
                       │                                                     │
                       ▼                                                     ▼
        ┌──────────────────────────────┐                      ┌──────────────────────────────┐
        │ knowledge_base/ is ready     │                      │ documents table updated      │
        │ Uploaded docs stored here    │                      │ indexing_status              │
        │                              │                      │ error_message                │
        │                              │                      │ chunk_count                  │
        └──────────────┬───────────────┘                      └──────────────┬───────────────┘
                       │                                                     │
                       └──────────────────────────┬──────────────────────────┘
                                                  ▼
                                   ┌──────────────────────────────┐
                                   │       Backend is Ready       │
                                   └──────────────────────────────┘



# FLOW 1: USER UPLOADS A DOCUMENT


┌───────────────────────────────┐
│ User selects files in UI      │
│ PDF/DOCX/XLSX/CSV/PPTX/TXT/MD │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Frontend uploadFiles()        │
│ Creates FormData              │
│ formData.append("files",file) │
└──────────────┬────────────────┘
               │
               ▼
┌──────────────────────────────┐
│ POST /upload                 │
│ FastAPI receives files       │
└──────────────┬───────────────┘
               │
               ▼
┌───────────────────────────────┐
│ ensure_folders()              │
│ Confirms knowledge_base exists│
└──────────────┬────────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Read uploaded files from form│
│ form.getlist("files")        │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ For each uploaded file       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ safe_filename = basename     │
│ Prevents unsafe path usage   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ save_path = knowledge_base/  │
│ File saved in knowledge_base │
└──────────────┬───────────────┘
               │
               ▼
        ┌──────────────────────┐
        │ is_supported_file()? │
        └──────────┬───────────┘
                   │
        ┌──────────┴───────────┐
        │                      │
        ▼                      ▼
┌───────────────┐     ┌──────────────────────────────┐
│ NO            │     │ YES                          │
│ unsupported   │     │ queue_file_for_indexing()    │
│ return status │     └──────────────┬───────────────┘
└───────────────┘                    │
                                     ▼
                      ┌──────────────────────────────┐
                      │ Calculate metadata           │
                      │ file_size                    │
                      │ last_modified                │
                      │ SHA256 hash                  │
                      └──────────────┬───────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────┐
                      │ Check documents table by path│
                      │ WHERE file_path = save_path  │
                      └──────────────┬───────────────┘
                                     │
              ┌──────────────────────┴────────────────────────┐
              │                                               │
              ▼                                               ▼
┌──────────────────────────────┐                ┌──────────────────────────────┐
│ Same path exists             │                │ Same path does not exist     │
└──────────────┬───────────────┘                └──────────────┬───────────────┘
               │                                               │
               ▼                                               ▼
┌──────────────────────────────┐                ┌──────────────────────────────┐
│ Compare old hash/size/time   │                │ Check same hash in DB        │
└──────────────┬───────────────┘                │ WHERE file_hash = current    │
               │                                └──────────────┬───────────────┘
        ┌──────┴───────────────┐                               │
        │                      │                      ┌─────────┴─────────────┐
        ▼                      ▼                      │                       │
┌────────────────┐  ┌───────────────────────────┐     ▼                       ▼
│ Same content   │  │ Content changed           │ ┌────────────────┐  ┌──────────────────────────────┐
│ status ready?  │  │ version = version + 1     │ │ Same hash found│  │ Completely new file          │
└───────┬────────┘  │ status = pending          │ └───────┬────────┘  └──────────────┬───────────────┘
        │           │ scheduled = true          │         │                          │
        ▼           └──────────────┬────────────┘         ▼                          ▼
┌────────────────┐                 │             ┌────────────────┐      ┌──────────────────────────────┐
│ Skip indexing  │                 │             │ Duplicate file │      │ Insert row into documents    │
│ Return skipped │                 │             │ Skip indexing  │      │ status = pending             │
└────────────────┘                 │             └────────────────┘      │ chunk_count = 0              │
                                   │                                     │ error_message = NULL         │
                                   │                                     └──────────────┬───────────────┘
                                   │                                                     │
                                   └──────────────────────────┬──────────────────────────┘
                                                              ▼
                                           ┌──────────────────────────────┐
                                           │ background_tasks.add_task()  │
                                           │ process_document_indexing()  │
                                           └──────────────┬───────────────┘
                                                          │
                                                          ▼
                                           ┌──────────────────────────────┐
                                           │ Upload API returns quickly   │
                                           │ "Indexing in background"     │
                                           └──────────────────────────────┘



# FLOW 2: BACKGROUND INDEXING

┌──────────────────────────────┐
│ process_document_indexing()  │
│ Runs in background           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ update_document_status()     │
│ status = indexing            │
│ chunk_count = 0              │
│ error_message = NULL         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ extract_text(file_path)      │
│ Detects file extension       │
└──────────────┬───────────────┘
               │
 ┌─────────────┼─────────────────────────────────────────────────────┐
 ▼             ▼             ▼             ▼            ▼            ▼
PDF           DOCX          XLSX          CSV          PPTX         TXT/MD
 │             │             │             │            │            │
 ▼             ▼             ▼             ▼            ▼            ▼
fitz          python-docx    openpyxl      csv.reader   pptx         open()
 │             │             │             │            │            │
 └─────────────┴─────────────┴─────────────┴────────────┴────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Raw extracted text           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ clean_text()                 │
│ remove \r                    │
│ normalize spaces             │
│ normalize extra newlines     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ split_text_into_chunks()     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ recursive_split()            │
│ Tries to split naturally by: │
│ paragraph → line → sentence  │
│ semicolon → comma → space    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ add_overlap()                │
│ Adds 100 char overlap        │
│ Prevents context break       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Final chunks ready           │
│ Example: 2745 chunks         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Open PostgreSQL connection   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ DELETE old chunks            │
│ WHERE document_id = current  │
│ Used for re-indexing/version │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Process chunks in batches    │
│ EMBEDDING_BATCH_SIZE = 16    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ generate_embeddings_batch()  │
│ Calls Ollama /api/embed      │
│ input = [chunk1..chunk16]    │
└──────────────┬───────────────┘
               │
      ┌────────┴───────────┐
      │                    │
      ▼                    ▼
┌──────────────┐   ┌──────────────────────────────┐
│ Batch works  │   │ Batch fails                  │
│ embeddings[] │   │ fallback generate_embedding()│
└──────┬───────┘   └──────────────┬───────────────┘
       │                          │
       └────────────┬─────────────┘
                    ▼
     ┌──────────────────────────────┐
     │ Prepare rows for DB insert   │
     │ document_id                  │
     │ chunk_number                 │
     │ content                      │
     │ embedding vector             │
     │ token_count                  │
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │ execute_values()             │
     │ Bulk insert into             │
     │ document_chunks              │
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │ All batches completed        │
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │ update_document_status()     │
     │ status = ready               │
     │ chunk_count = inserted_count │
     │ error_message = NULL         │
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │ Document is searchable       │
     └──────────────────────────────┘


If any error happens:
               │
               ▼
┌──────────────────────────────┐
│ Exception caught             │
│ status = failed              │
│ error_message = actual error │
│ chunk_count = 0              │
└──────────────────────────────┘



# FLOW 3: FRONTEND DOCUMENT STATUS

┌──────────────────────────────┐
│ Frontend calls GET /documents│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Backend reads documents table│
│ returns:                     │
│ document_id                  │
│ filename                     │
│ source_type                  │
│ version                      │
│ indexing_status              │
│ error_message                │
│ chunk_count                  │
└──────────────┬───────────────┘
               │
               ▼
        ┌───────────────────────┐
        │ Frontend checks status│
        └──────────┬────────────┘
                   │
      ┌────────────┼─────────────┐
      ▼            ▼             ▼
READY             PENDING/INDEXING FAILED
 │                │                │
 ▼                ▼                ▼
Checkbox enabled  Checkbox disabled Checkbox disabled
Green badge       Auto-refresh       Show error
Can ask question  every 5 seconds    Cannot ask



# FLOW 4: USER ASKS QUESTION


┌──────────────────────────────┐
│ User types question          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Frontend validateBeforeSend()│
└──────────────┬───────────────┘
               │
      ┌────────┴─────────────────────────────────┐
      │                                          │
      ▼                                          ▼
┌──────────────────────────────┐       ┌──────────────────────────────┐
│ No ready document available  │       │ Ready document available     │
│ Show warning                 │       │ Continue                     │
└──────────────────────────────┘       └──────────────┬───────────────┘
                                                      │
                                                      ▼
                                   ┌──────────────────────────────┐
                                   │ Build payload                │
                                   │ question                     │
                                   │ session_id                   │
                                   │ document_ids                 │
                                   └──────────────┬───────────────┘
                                                  │
                                                  ▼
                                   ┌──────────────────────────────┐
                                   │ POST /chat                   │
                                   └──────────────┬───────────────┘
                                                  │
                                                  ▼
                                   ┌──────────────────────────────┐
                                   │ create_session_if_needed()   │
                                   └──────────────┬───────────────┘
                                                  │
                      ┌───────────────────────────┴───────────────────────────┐
                      ▼                                                       ▼
       ┌──────────────────────────────┐                        ┌──────────────────────────────┐
       │ session_id exists            │                        │ session_id is NULL           │
       │ Continue old chat            │                        │ Create new chat_sessions row │
       └──────────────┬───────────────┘                        └──────────────┬───────────────┘
                      │                                                       │
                      └───────────────────────────┬───────────────────────────┘
                                                  ▼
                                   ┌──────────────────────────────┐
                                   │ save_message()               │
                                   │ role = user                  │
                                   │ message = question           │
                                   └──────────────┬───────────────┘
                                                  │
                                                  ▼
                                   ┌──────────────────────────────┐
                                   │ retrieve_relevant_chunks()   │
                                   └──────────────────────────────┘



# FLOW 5: BALANCED MULTI-DOCUMENT RETRIEVAL

┌──────────────────────────────┐
│ retrieve_relevant_chunks()   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Determine document scope     │
└──────────────┬───────────────┘
               │
       ┌───────┴────────────────┐
       │                        │
       ▼                        ▼
┌──────────────────────┐  ┌──────────────────────────────┐
│ document_ids provided│  │ document_ids empty           │
│ Use selected docs    │  │ get_ready_document_ids()     │
│ only                 │  │ Use all ready documents      │
└──────────┬───────────┘  └──────────────┬───────────────┘
           │                             │
           └──────────────┬──────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ target_document_ids ready    │
           └──────────────┬───────────────┘
                          │
                          ▼
           ┌──────────────────────────────┐
           │ For EACH document_id         │
           └──────────────┬───────────────┘
                          │
          ┌───────────────┼───────────────────────────────┐
          ▼               ▼                               ▼
┌────────────────┐ ┌────────────────────────┐ ┌──────────────────────────────┐
│ Vector Search  │ │ Keyword Search         │ │ Merge Results                │
│ meaning search │ │ exact word search      │ │ remove duplicate chunks      │
└───────┬────────┘ └───────────┬────────────┘ └──────────────┬───────────────┘
        │                      │                             │
        ▼                      ▼                             ▼
┌────────────────┐ ┌────────────────────────┐ ┌──────────────────────────────┐
│ Generate       │ │ tokenize(question)     │ │ chunk_id used as unique key  │
│ question vector│ │ ILIKE matching         │ └──────────────┬───────────────┘
└───────┬────────┘ └───────────┬────────────┘                │
        │                      │                             ▼
        ▼                      ▼              ┌──────────────────────────────┐
┌─────────────────────────────────────┐       │ rerank_chunks()              │
│ Search document_chunks with pgvector│       │ final_score =                │
│ embedding <=> question_embedding    │       │ keyword_hits                 │
└─────────────────────────────────────┘       │ + vector_score               │
                                              │ + source_bonus               │
                                              │ + exact_phrase_bonus         │
                                              └──────────────┬───────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │ Pick top direct chunks       │
                                              │ PER_DOCUMENT_DIRECT_TOP_K    │
                                              └──────────────┬───────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │ fetch_neighbor_chunks()      │
                                              │ If chunk 10 selected         │
                                              │ include 8,9,10,11,12         │
                                              └──────────────┬───────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │ build_context_chunks_for_doc │
                                              │ Sort by chunk_number         │
                                              │ Limit per document           │
                                              │ Limit per document           │
                                              └──────────────┬───────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │ Add to final context chunks  │
                                              └──────────────┬───────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │ Repeat for next document     │
                                              └──────────────┬───────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │ Final context from all docs  │
                                              │ Max 32 chunks total          │
                                              └──────────────────────────────┘



# FLOW 6: LLM ANSWER GENERATION

┌──────────────────────────────┐
│ generate_answer()            │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Build context_parts          │
│ Source 1                     │
│ Document ID                  │
│ File                         │
│ Chunk                        │
│ Content                      │
└──────────────┬───────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Build system_prompt           │
│ Rules:                        │
│ - use only KB content         │
│ - do not hallucinate          │
│ - consider all docs           │
│ - mention doc-wise difference │
└──────────────┬────────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Build user_prompt            │
│ Context + User question      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ POST Ollama /api/chat        │
│ model = qwen2.5:7b           │
│ stream = false               │
└──────────────┬───────────────┘
               │
       ┌───────┴───────────┐
       │                   │
       ▼                   ▼
┌──────────────┐    ┌──────────────────────────────┐
│ Success      │    │ Failed                       │
│ answer text  │    │ raise Chat model failed      │
└──────┬───────┘    └──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ save_message()               │
│ role = assistant             │
│ message = answer             │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Return response to frontend  │
│ answer                       │
│ sources                      │
│ session_id                   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Frontend displays            │
│ answer + source cards        │
└──────────────────────────────┘



# FLOW 7: CHAT HISTORY

┌──────────────────────────────┐
│ GET /sessions                │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Read chat_sessions table     │
│ return all sessions          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Frontend shows chat history  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ User clicks one session      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ GET /sessions/{id}/messages  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Read chat_messages table     │
│ role=user/assistant          │
│ message                      │
│ created_at                   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Frontend reloads conversation│
└──────────────────────────────┘
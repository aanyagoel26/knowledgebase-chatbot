# KnowledgeBase Chatbot 
                                        START
                                           │
                                           ▼
                              FastAPI Server Starts
                                           │
                                           ▼
                           Connect PostgreSQL + pgvector
                                           │
                                           ▼
                          Load LLM + Embedding Model (Ollama)
                                           │
                                           ▼
                     ┌─────────────────────┴─────────────────────┐
                     │                                           │
                     ▼                                           ▼
          Knowledge Base Indexing                     User Uploads Documents
                     │                                           │
                     ▼                                           ▼
         Scan knowledge_base folder                  Receive uploaded files
                     │                                           │
                     ▼                                           ▼
             Pick one document                         Save in uploads folder
                     │                                           │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                           Check if file_path exists in DB
                                           │
                     ┌─────────────────────┴─────────────────────┐
                     │                                           │
                   YES                                           NO
                     │                                           │
                     ▼                                           ▼
        Compare file_size + last_modified            Calculate File Hash
                     │                                           │
          ┌──────────┴──────────┐                               │
          │                     │                               ▼
        Same                Changed                  Check hash in DB
          │                     │                               │
          ▼                     ▼                ┌──────────────┴──────────────┐
      Skip File          Calculate Hash          │                             │
                                │              Exists                      Doesn't Exist
                                │                 │                             │
                      ┌─────────┴─────────┐       │                             │
                      │                   │       ▼                             ▼
                  Hash Same         Hash Different                  New Unique Document
                      │                   │                             │
                      ▼                   ▼                             ▼
              Skip Re-index      Updated Document             Insert into documents table
                                          │                             │
                                          ▼                             ▼
                            Get document_id                    Extract Text
                                          │                             │
                                          ▼                             ▼
                          Delete old chunks                 Clean & Normalize Text
                          using document_id                           │
                                          │                             ▼
                                          ▼                    Intelligent Chunking
                                   Extract Text                         │
                                          │                             ▼
                                          ▼                  Generate Embeddings
                              Clean & Normalize Text                   │
                                          │                             ▼
                                          ▼                Store in document_chunks
                              Intelligent Chunking                    │
                                          │                             │
                                          ▼                             │
                               Generate Embeddings                     │
                                          │                             │
                                          ▼                             │
                              Store new document_chunks ◄───────────────┘
                                          │
                                          ▼
                               KNOWLEDGE BASE READY
                                          │
                                          ▼
═══════════════════════════════════════════════════════════════════════════════
                                          │
                                          ▼
                              USER ASKS A QUESTION
                                          │
                                          ▼
                           Store question in chat_messages
                                          │
                                          ▼
                          Generate Question Embedding
                                          │
                     ┌────────────────────┴────────────────────┐
                     │                                         │
                     ▼                                         ▼
            Vector Search (pgvector)              Keyword Search (SQL)
                     │                                         │
                     └────────────────────┬────────────────────┘
                                          │
                                          ▼
                                Merge Candidate Chunks
                                          │
                                          ▼
                              Intelligent Re-ranking
                                          │
                                          ▼
                          Select Top Relevant Chunks (Top K)
                                          │
                                          ▼
                           Build Context + Source Metadata
                                          │
                                          ▼
                               Send to qwen2.5:7b LLM
                                          │
                                          ▼
                          Generate Grounded Final Answer
                                          │
                                          ▼
                       Store Answer in chat_messages table
                                          │
                                          ▼
                 Return Answer + Sources + Chat History to UI
                                          │
                                          ▼
                                         END

from app.database.connection import get_db_connection
from app.services.auth.auth_service import hash_password


def ensure_schema_updates():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            document_id SERIAL PRIMARY KEY,
            original_filename TEXT NOT NULL,
            file_path TEXT UNIQUE NOT NULL,
            file_hash TEXT NOT NULL,
            file_size BIGINT,
            last_modified TIMESTAMP,
            source_type TEXT DEFAULT 'knowledge_base',
            version INTEGER DEFAULT 1,
            indexing_status TEXT DEFAULT 'pending',
            error_message TEXT,
            chunk_count INTEGER DEFAULT 0,
            indexed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            chunk_id SERIAL PRIMARY KEY,
            document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE,
            chunk_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector(768),
            token_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id SERIAL PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            employee_id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',
            role TEXT DEFAULT 'employee',
            department TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_sessions
        ADD COLUMN IF NOT EXISTS employee_id INTEGER REFERENCES employees(employee_id) ON DELETE CASCADE;
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_sessions
        ADD COLUMN IF NOT EXISTS assistant_mode TEXT DEFAULT 'knowledge';
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_messages
        ADD COLUMN IF NOT EXISTS sources_json TEXT;
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_messages
        ADD COLUMN IF NOT EXISTS answer_payload_json TEXT;
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_sessions
        ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_sessions
        ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;
        """
    )

    cursor.execute(
        """
        ALTER TABLE chat_sessions
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_sessions (
            session_id SERIAL PRIMARY KEY,
            employee_id INTEGER REFERENCES employees(employee_id) ON DELETE CASCADE,
            session_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_login_logs (
            log_id SERIAL PRIMARY KEY,
            employee_id INTEGER REFERENCES employees(employee_id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            logout_time TIMESTAMP,
            ip_address TEXT,
            status TEXT DEFAULT 'active'
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS indexing_status TEXT DEFAULT 'ready';
        """
    )

    cursor.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS error_message TEXT;
        """
    )

    cursor.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0;
        """
    )

    cursor.execute(
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS department TEXT;
        """
    )

    cursor.execute(
        """
        ALTER TABLE employees
        ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
        """
    )

    cursor.execute(
        """
        UPDATE employees
        SET is_active = TRUE
        WHERE is_active IS NULL;
        """
    )

    cursor.execute(
        """
        INSERT INTO employees(name, email, password_hash, role, department, is_active)
        VALUES (%s, %s, %s, %s, %s, TRUE)
        ON CONFLICT(email) DO NOTHING;
        """,
        (
            "Admin",
            "admin@motherson.com",
            hash_password("admin123"),
            "admin",
            "IT"
        )
    )

    conn.commit()
    cursor.close()
    conn.close()
import hashlib

import requests
from fastapi import HTTPException, Request

from app.config.settings import (
    ALLOWED_EMPLOYEE_EMAIL_DOMAINS,
    AUTH_MODE,
    COMPANY_EMPLOYEE_VERIFY_URL
)
from app.database.connection import get_db_connection


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_allowed_employee_email(email):
    email = email.strip().lower()

    return any(
        email.endswith(domain)
        for domain in ALLOWED_EMPLOYEE_EMAIL_DOMAINS
    )


def verify_employee_locally(email, password):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT employee_id, name, email, role, department
        FROM employees
        WHERE email = %s
          AND password_hash = %s
          AND is_active = TRUE
        """,
        (
            email,
            hash_password(password)
        )
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return None

    return {
        "employee_id": row[0],
        "name": row[1],
        "email": row[2],
        "role": row[3],
        "department": row[4]
    }


def verify_employee_from_company_system(email, password):
    if not COMPANY_EMPLOYEE_VERIFY_URL:
        raise HTTPException(
            status_code=500,
            detail="Company employee verification API is not configured."
        )

    try:
        response = requests.post(
            COMPANY_EMPLOYEE_VERIFY_URL,
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )
    except Exception:
        return None

    if response.status_code != 200:
        return None

    data = response.json()

    if not data.get("valid"):
        return None

    return {
        "employee_id": data.get("employee_id"),
        "name": data.get("name"),
        "email": data.get("email"),
        "role": data.get("role", "employee"),
        "department": data.get("department")
    }


def get_session_token(request: Request):
    return request.cookies.get("kb_session_token")


def require_login(request: Request):
    token = get_session_token(request)

    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT e.employee_id, e.name, e.email, e.role, e.department
        FROM employee_sessions s
        JOIN employees e
        ON s.employee_id = e.employee_id
        WHERE s.session_token = %s
          AND e.is_active = TRUE
        """,
        (token,)
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid session")

    return {
        "employee_id": row[0],
        "name": row[1],
        "email": row[2],
        "role": row[3],
        "department": row[4]
    }
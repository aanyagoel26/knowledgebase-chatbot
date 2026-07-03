import uuid

from fastapi import APIRouter, Request, Response, HTTPException

from app.database.connection import get_db_connection
from app.config.settings import AUTH_MODE
from models import LoginRequest
from auth import (
    hash_password,
    is_allowed_employee_email,
    verify_employee_locally,
    verify_employee_from_company_system,
    get_session_token,
    require_login
)

router = APIRouter()


@router.post("/login")
def login(
        request: LoginRequest,
        response: Response,
        http_request: Request):

    email = request.email.strip().lower()

    if not is_allowed_employee_email(email):
        raise HTTPException(
            status_code=403,
            detail="Only approved Motherson employees can login."
        )

    if AUTH_MODE == "company":
        employee = verify_employee_from_company_system(email, request.password)
    else:
        employee = verify_employee_locally(email, request.password)

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee not found or password is incorrect."
        )

    session_token = str(uuid.uuid4())

    ip_address = (
        http_request.client.host
        if http_request.client
        else None
    )

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO employees
        (
            name,
            email,
            password_hash,
            role,
            department,
            is_active
        )
        VALUES (%s,%s,%s,%s,%s,TRUE)
        ON CONFLICT(email)
        DO UPDATE SET
            name=EXCLUDED.name,
            role=EXCLUDED.role,
            department=EXCLUDED.department,
            is_active=TRUE
        RETURNING employee_id
        """,
        (
            employee["name"],
            employee["email"],
            "" if AUTH_MODE == "company" else hash_password(request.password),
            employee.get("role", "employee"),
            employee.get("department")
        )
    )

    employee_id = cursor.fetchone()[0]

    cursor.execute(
        """
        DELETE FROM employee_sessions
        WHERE employee_id=%s
        """,
        (employee_id,)
    )

    cursor.execute(
        """
        UPDATE employee_login_logs
        SET logout_time=CURRENT_TIMESTAMP,
            status='logged_out'
        WHERE employee_id=%s
          AND logout_time IS NULL
        """,
        (employee_id,)
    )

    cursor.execute(
        """
        INSERT INTO employee_sessions
        (
            employee_id,
            session_token
        )
        VALUES (%s,%s)
        """,
        (
            employee_id,
            session_token
        )
    )

    cursor.execute(
        """
        INSERT INTO employee_login_logs
        (
            employee_id,
            email,
            ip_address,
            status
        )
        VALUES (%s,%s,%s,'active')
        """,
        (
            employee_id,
            employee["email"],
            ip_address
        )
    )

    conn.commit()
    cursor.close()
    conn.close()

    response.set_cookie(
        key="kb_session_token",
        value=session_token,
        httponly=True,
        samesite="lax"
    )

    employee["employee_id"] = employee_id

    return {
        "message": "Login successful",
        "employee": employee
    }


@router.post("/logout")
def logout(request: Request, response: Response):

    token = get_session_token(request)

    if token:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT e.employee_id, e.email
            FROM employee_sessions s
            JOIN employees e
            ON s.employee_id=e.employee_id
            WHERE s.session_token=%s
            """,
            (token,)
        )

        row = cursor.fetchone()

        if row:
            cursor.execute(
                """
                UPDATE employee_login_logs
                SET logout_time=CURRENT_TIMESTAMP,
                    status='logged_out'
                WHERE employee_id=%s
                  AND email=%s
                  AND logout_time IS NULL
                """,
                (
                    row[0],
                    row[1]
                )
            )

        cursor.execute(
            """
            DELETE FROM employee_sessions
            WHERE session_token=%s
            """,
            (token,)
        )

        conn.commit()
        cursor.close()
        conn.close()

    response.delete_cookie("kb_session_token")

    return {
        "message": "Logged out"
    }


@router.get("/me")
def me(request: Request):
    employee = require_login(request)

    return {
        "employee": employee
    }
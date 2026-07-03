import uuid

from fastapi import APIRouter, Request, Response, HTTPException
from app.config.settings import AUTH_MODE
from models import LoginRequest
from app.services.auth_service import (
    hash_password,
    is_allowed_employee_email,
    verify_employee_locally,
    verify_employee_from_company_system,
    get_session_token,
    require_login
)
from app.database.repository import (
    upsert_employee_after_login,
    create_employee_session,
    logout_employee_session
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
    
    employee_id = upsert_employee_after_login(
        employee,
        "" if AUTH_MODE == "company" else hash_password(request.password)
    )

    create_employee_session(
        employee_id,
        employee["email"],
        session_token,
        ip_address
    )

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
        logout_employee_session(token)

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
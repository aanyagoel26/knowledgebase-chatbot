import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from app.config.settings import AUTH_MODE
from app.database.repository import (
    create_employee_account,
    create_employee_session,
    logout_employee_session,
    upsert_employee_after_login
)
from app.models.request_models import LoginRequest, SignupRequest
from app.services.auth.auth_service import (
    get_session_token,
    hash_password,
    is_allowed_employee_email,
    require_login,
    verify_employee_from_company_system,
    verify_employee_locally
)
router = APIRouter()


@router.post("/signup")
def signup(request: SignupRequest):
    name = request.name.strip()
    email = request.email.strip().lower()
    password = request.password

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Name is required."
        )

    if not is_allowed_employee_email(email):
        raise HTTPException(
            status_code=403,
            detail="Only approved Motherson employee emails can sign up."
        )

    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters."
        )

    employee_id = create_employee_account(
        name=name,
        email=email,
        password_hash=hash_password(password),
        department=request.department
    )

    if employee_id is None:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    return {
        "message": "Account created successfully. Please sign in."
    }


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
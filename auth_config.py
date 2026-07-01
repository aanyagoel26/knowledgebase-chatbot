import os

AUTH_MODE = os.getenv("AUTH_MODE", "local")

COMPANY_EMPLOYEE_VERIFY_URL = os.getenv(
    "COMPANY_EMPLOYEE_VERIFY_URL",
    ""
)

ALLOWED_EMPLOYEE_EMAIL_DOMAINS = [
    "@motherson.com",
    "@mtsl.com"
]
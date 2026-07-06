from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.config.settings import UI_FILE

from app.core.startup import startup_event
from app.core.middleware import RequestLoggingMiddleware

from app.routes.auth_routes import router as auth_router
from app.routes.document_routes import router as document_router
from app.routes.chat_routes import router as chat_router
from app.routes.database_routes import router as database_router
from app.routes.session_routes import router as session_router


app = FastAPI()

app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(chat_router)
app.include_router(database_router)
app.include_router(session_router)


@app.on_event("startup")
def app_startup():
    startup_event()


@app.get("/")
def home():
    return FileResponse(UI_FILE)


@app.get("/health")
def health_check():
    return {
        "status": "Backend is running"
    }
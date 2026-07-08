from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config.settings import UI_FILE
from app.core.middleware import RequestLoggingMiddleware
from app.core.startup import startup_event
from app.api.auth_routes import router as auth_router
from app.api.chat_routes import router as chat_router
from app.api.database_routes import router as database_router
from app.api.document_routes import router as document_router
from app.api.session_routes import router as session_router


app = FastAPI()

app.add_middleware(RequestLoggingMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")
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
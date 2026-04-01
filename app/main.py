"""BizAI FastAPI app with auth, chat memory controls, file upload, and RAG."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import _send_email, run_business_agent
from app.auth import (
    authenticate_user,
    create_access_token,
    create_oauth_state,
    create_user,
    ensure_oauth_user,
    init_auth_db,
    verify_oauth_state,
    verify_access_token,
)
from app.knowledge import delete_knowledge, ingest_file, knowledge_stats
from app.session_store import (
    append_turn,
    clear_session,
    create_session,
    delete_session,
    get_history,
    list_sessions,
)
from app.db import update_session_name

load_dotenv()
init_auth_db()

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
FRONTEND_DIST = ROOT / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets" if (FRONTEND_DIST / "assets").is_dir() else STATIC

app = FastAPI(title="BizAI", description="Business AI agent API")

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    email: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32000)
    session_id: str | None = None
    enable_web_search: bool = False


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class SessionResponse(BaseModel):
    session_id: str


class SessionListItem(BaseModel):
    id: str
    name: str
    preview: str = ""
    updated_at: str = ""


class MessageItem(BaseModel):
    role: str
    content: str


class UploadResponse(BaseModel):
    filename: str
    chunks_added: int
    chunks_total: int
    documents_total: int


class EmailSendRequest(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=320)
    body: str = Field(min_length=1, max_length=20000)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise HTTPException(status_code=503, detail=f"{name} is not configured")
    return value


def _google_redirect_uri() -> str:
    configured = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        return configured
    base_url = _require_env("APP_BASE_URL").rstrip("/")
    return f"{base_url}/api/auth/google/callback"


def _app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", "").strip().rstrip("/")


def _json_request(url: str, data: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> dict:
    payload = None
    merged_headers = {"Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    if data is not None:
        payload = urlencode(data).encode("utf-8")
    request = Request(url, data=payload, headers=merged_headers)
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return verify_access_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@app.post("/api/auth/signup", response_model=AuthResponse)
async def signup(body: AuthRequest) -> AuthResponse:
    try:
        create_user(body.email, body.password)
        email = authenticate_user(body.email, body.password)
        token = create_access_token(email)
        return AuthResponse(access_token=token, email=email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/auth/signin", response_model=AuthResponse)
async def signin(body: AuthRequest) -> AuthResponse:
    try:
        email = authenticate_user(body.email, body.password)
        token = create_access_token(email)
        return AuthResponse(access_token=token, email=email)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@app.get("/api/auth/google/start")
async def google_start() -> dict[str, str]:
    client_id = _require_env("GOOGLE_CLIENT_ID")
    redirect_uri = _google_redirect_uri()
    state = create_oauth_state("google")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return {"auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


@app.get("/api/auth/google/callback")
async def google_callback(code: str | None = None, state: str | None = None) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Google OAuth code or state")
    provider = verify_oauth_state(state)
    if provider != "google":
        raise HTTPException(status_code=400, detail="OAuth provider mismatch")

    redirect_uri = _google_redirect_uri()
    token_data = _json_request(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": _require_env("GOOGLE_CLIENT_ID"),
            "client_secret": _require_env("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = str(token_data.get("access_token", "")).strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Google OAuth token exchange failed")

    profile = _json_request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    email = ensure_oauth_user(str(profile.get("email", "")))
    app_token = create_access_token(email)
    redirect_params = urlencode({"oauth_token": app_token, "oauth_email": email})
    base_url = _app_base_url()
    auth_url = f"{base_url}/auth?{redirect_params}" if base_url else f"/auth?{redirect_params}"
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/api/auth/me")
async def me(user_email: str = Depends(get_current_user)) -> dict[str, str]:
    return {"email": user_email}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user_email: str = Depends(get_current_user)) -> ChatResponse:
    try:
        sid = body.session_id
        is_new = False
        if not sid:
            sid = create_session(user_email)
            is_new = True
            
        history = get_history(sid, user_email)
        if not history and not is_new:
            is_new = True
            
        if is_new:
            name_str = (body.message[:35] + "...") if len(body.message) > 35 else body.message
            update_session_name(sid, user_email, name_str)
            
        reply = run_business_agent(
            user_message=body.message,
            history=history,
            user_email=user_email,
            enable_web_search=body.enable_web_search,
        )
        append_turn(sid, user_email, "user", body.message)
        append_turn(sid, user_email, "assistant", reply)
        return ChatResponse(reply=reply, session_id=sid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e!s}") from e


@app.get("/api/chat/sessions")
async def sessions(user_email: str = Depends(get_current_user)) -> dict[str, list[SessionListItem]]:
    return {"sessions": list_sessions(user_email)}


@app.get("/api/chat/{session_id}/messages")
async def session_messages(session_id: str, user_email: str = Depends(get_current_user)) -> dict[str, list[MessageItem]]:
    try:
        history = get_history(session_id, user_email)
        return {"messages": [MessageItem(role=item["role"], content=item["content"]) for item in history]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/chat/new", response_model=SessionResponse)
async def new_session(user_email: str = Depends(get_current_user)) -> SessionResponse:
    return SessionResponse(session_id=create_session(user_email))


@app.post("/api/chat/{session_id}/clear")
async def clear(session_id: str, user_email: str = Depends(get_current_user)) -> dict[str, str]:
    try:
        clear_session(session_id, user_email)
        return {"status": "cleared"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.delete("/api/chat/{session_id}")
async def remove(session_id: str, user_email: str = Depends(get_current_user)) -> dict[str, str]:
    try:
        delete_session(session_id, user_email)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/knowledge/upload", response_model=UploadResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    user_email: str = Depends(get_current_user),
) -> UploadResponse:
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")
    try:
        added = ingest_file(
            user_email,
            filename=file.filename or "uploaded-file",
            content_type=file.content_type or "",
            data=data,
        )
        if session_id and file.filename:
            update_session_name(session_id, user_email, file.filename)
            
        stats = knowledge_stats(user_email)
        return UploadResponse(
            filename=file.filename or "uploaded-file",
            chunks_added=added,
            chunks_total=stats["chunks"],
            documents_total=stats["documents"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload failed: {e!s}") from e


@app.delete("/api/knowledge")
async def wipe_knowledge(user_email: str = Depends(get_current_user)) -> dict[str, str]:
    delete_knowledge(user_email)
    return {"status": "deleted"}


@app.post("/api/email/send")
async def send_email_message(body: EmailSendRequest, user_email: str = Depends(get_current_user)) -> dict[str, str]:
    try:
        result = _send_email(body.to.strip(), body.subject.strip(), body.body.strip())
        return {"status": "sent", "detail": result, "requested_by": user_email}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Email send failed: {e!s}") from e


@app.post("/api/email/send-with-attachment")
async def send_email_with_attachment(
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    user_email: str = Depends(get_current_user),
) -> dict[str, str]:
    try:
        attachments = []
        if attachment is not None:
            attachments.append(
                {
                    "filename": attachment.filename or "attachment",
                    "content_type": attachment.content_type or "application/octet-stream",
                    "content": await attachment.read(),
                }
            )
        result = _send_email(
            to.strip(),
            subject.strip(),
            body.strip(),
            attachments=attachments,
        )
        return {"status": "sent", "detail": result, "requested_by": user_email}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Email send failed: {e!s}") from e


@app.get("/api/health")
async def health() -> dict[str, str]:
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    has_database = bool(os.environ.get("DATABASE_URL"))
    has_google = bool(os.environ.get("GOOGLE_CLIENT_ID"))
    return {
        "status": "ok" if has_key else "missing_api_key",
        "database": "postgres" if has_database else "sqlite",
        "google_oauth": "configured" if has_google else "not_configured",
    }


if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


def _serve_page(filename: str) -> FileResponse:
    spa_index = FRONTEND_DIST / "index.html"
    if spa_index.is_file():
        return FileResponse(spa_index)
    path = STATIC / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="UI not built")
    return FileResponse(path)


@app.get("/")
async def index() -> FileResponse:
    return _serve_page("auth.html")


@app.get("/auth")
async def auth_page() -> FileResponse:
    return _serve_page("auth.html")


@app.get("/chat")
async def chat_page() -> FileResponse:
    return _serve_page("chat.html")

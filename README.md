# BizAI : AI Business Workspace


<img width="1897" height="902" alt="image" src="https://github.com/user-attachments/assets/1ad06627-c298-4ccd-babe-8759f391cd9e" />
<img width="1871" height="923" alt="image" src="https://github.com/user-attachments/assets/1be3c190-1099-4eb1-b659-4c0693f4c367" />




BizAI is a fully containerized, production-ready AI Assistant designed for enterprise workflows. It combines a premium glassmorphic UI with a powerful Python backend.

## Core Features
* Built a modern, highly-responsive full-stack AI platform and API using **React, Vite, and FastAPI**.
* Engineered an end-to-end custom RAG indexing and document search pipeline using **LangChain** and **OpenAI**.
* Secured user authentication and persistent multi-user chat state with **PostgreSQL, JWTs, and Google OAuth**.
* Containerized the application with **Docker Compose** for seamless end-to-end orchestration and production deployment.
* **Auto-naming Threads:** Intelligent chat session naming based on uploaded document names or the user's first prompt.

## Quick Start (Local Development)

If you are running manually *outside* of Docker for development:

1. Install backend dependencies:
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

2. Build the React frontend:
```bash
cd frontend
npm install
npm run build
cd ..
```

3. Configure your `.env` file (see `.env.example`).
*Note: You can leave `DATABASE_URL` empty to automatically fall back to local SQLite, or point it directly to your local PostgreSQL instance.*

4. Start the FastAPI server:
```bash
uvicorn app.main:app --port 8000
```

Open: <http://127.0.0.1:8000>

## Quick Start (Docker Production)

The entire application is production-ready and orchestrated via Docker Compose.

1. Ensure **Docker** and **Docker Compose** are installed on your machine.
2. Run the build command:
```bash
docker compose up --build -d
```
This single command spins up a secure PostgreSQL database container, mounts persistent volumes so you never lose your embeddings or chat history, builds the Vite frontend static files, and starts the full FastAPI server!

## Google OAuth Setup

To enable the "Continue with Google" button:
1. Generate an OAuth Client ID in Google Cloud Console.
2. Add your Client ID and Secret to `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
3. Ensure you add `http://localhost:8000/api/auth/google/callback` (or your true production domain) precisely to the **Authorized redirect URIs** list in the Google Cloud settings!

## RAG & Embeddings Architecture

When documents (`.pdf`, `.txt`, `.md`) are uploaded via the left sidebar, they are automatically chunked and mathematically embedded using **OpenAI's `text-embedding-3-small` model**. 

These vectors are seamlessly stored as raw JSON arrays directly inside PostgreSQL's `knowledge_chunks` table, allowing LangChain to perform lightning-fast Python-native Cosine Similarity semantic searches to power your agent's reasoning.

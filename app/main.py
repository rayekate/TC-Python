# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path            # <-- missing import
from dotenv import load_dotenv

from app.routers import auth
from app.routers import export as export_router

# Import opentele early so it patches Telethon before other modules import it
try:
    import opentele  # noqa: F401
except Exception as e:
    print(f"[warn] opentele pre-import failed: {e}")
    
# load .env before reading env vars
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Telegram Auth API", version="1.0.0")

origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(export_router.router)

@app.get("/health")
def health():
    return {"ok": True}

# app/__init__.py
from pathlib import Path
from dotenv import load_dotenv

# Load the project-root .env BEFORE other modules import os.getenv(...)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

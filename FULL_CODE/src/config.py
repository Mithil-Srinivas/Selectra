"""Paths and model settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]  # FULL_CODE/
ROOT_DIR = CODE_DIR.parent                       # project root (holds data/, evaluate.py)

DATA_DIR = Path(os.getenv("R3_DATA_DIR", ROOT_DIR / "data"))
ARTIFACT_DIR = Path(os.getenv("R3_ARTIFACT_DIR", CODE_DIR / "artifacts"))  # cached indexes, eval outputs

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://10.10.37.186:11434")
LLM_MODEL = os.getenv("OLLAMA_MODEL", "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")

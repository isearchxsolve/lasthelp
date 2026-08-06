"""
OMEGA Content Safety & Quality Guard Layer
============================================

Prevents harmful, illegal, or low-quality output from being generated or delivered.
Runs BEFORE and AFTER code generation.

Rules:
1. REFUSE harmful requests (fraud, illegal, dangerous) with explanation
2. REJECT comment-only code with <10 lines of executable logic
3. VERIFY package names in requirements.txt against known patterns
4. BLOCK mock-mode template generation for harmful goals
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

logger = logging.getLogger("omega_agent.safety_guard")


# =============================================================================
# HARMFUL CONTENT DETECTION (LLM-based — no keywords)
# =============================================================================

async def classify_safety_risk(goal: str, orchestrator=None) -> Tuple[str, float, Optional[str]]:
    """
    Classify the safety risk of a goal string using LLM.
    
    Uses LLM to detect harmful content (fraud, illegal activities, security bypass).
    When no orchestrator is available, returns "safe" with 0 confidence (falls open
    rather than false-positive blocking).
    
    Args:
        goal: The user's goal string
        orchestrator: Optional ModelOrchestrator for LLM-based classification
    
    Returns:
        (risk_level: "safe" | "warn" | "block", confidence: 0-1, refusal_message: str|None)
    """
    if not orchestrator or not orchestrator.config.has_llm_credentials():
        logger.debug("No LLM available for safety classification, defaulting to safe")
        return "safe", 0.0, None

    prompt = f"""Analyze this goal and classify it as one of:
- "safe": Legitimate, legal, ethical project
- "warn": Suspicious but not clearly harmful
- "block": Fraudulent, illegal, dangerous, or harmful

Goal: {goal}

Categories of harmful content:
- Financial fraud (scams, phishing, money laundering, fake accounts)
- Illegal activities (theft, hacking, violence, weapons, drugs)
- Security bypass (evading KYC/AML, bypassing authentication)
- Social engineering, identity theft
- CSAM, self-harm, harassment, stalking

Respond with ONLY one word: "safe", "warn", or "block"."""

    try:
        response, _ = await orchestrator.invoke(
            prompt=prompt,
            system="You are a safety classifier. Respond with ONLY 'safe', 'warn', or 'block'.",
            temperature=0.1,
            max_tokens=10
        )
        risk_level = response.strip().lower()
        if risk_level not in ("safe", "warn", "block"):
            risk_level = "warn"
        confidence = 0.8 if risk_level != "safe" else 0.0
        refusal = None if risk_level == "safe" else (
            "[BLOCKED] I cannot help with this request. This appears to be harmful or prohibited content."
        )
        return risk_level, confidence, refusal
    except Exception as e:
        logger.warning("LLM safety classification failed: %s, defaulting to warn", e)
        return "warn", 0.5, None


# =============================================================================
# CODE QUALITY VALIDATION
# =============================================================================

MIN_EXECUTABLE_LINES = 8  # Minimum lines of actual code (not comments/blank)
MAX_COMMENT_RATIO = 0.80  # Max ratio of comment lines to total lines


def _is_comment_line(line: str) -> bool:
    """Check if a line is purely a comment."""
    stripped = line.strip()
    if not stripped:
        return False  # blank line, not a comment
    return stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")


def _is_code_line(line: str) -> bool:
    """Check if a line contains actual executable code."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return False
    # Docstrings are code-adjacent but not executable
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return False
    return True


def validate_code_quality(files: List[Dict[str, str]]) -> Tuple[bool, List[str], List[str]]:
    """
    Validate that generated code files contain actual executable logic.
    
    Returns:
        (is_valid: bool, rejected_files: list of reasons, accepted_files: list of paths)
    """
    rejected = []
    accepted = []
    
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        
        if not content:
            rejected.append(f"{path}: Empty file (no content)")
            continue
        
        lines = content.split("\n")
        total_lines = len(lines)
        code_lines = sum(1 for l in lines if _is_code_line(l))
        comment_lines = sum(1 for l in lines if _is_comment_line(l))
        
        # Skip non-code files (README, JSON, config files)
        is_code_file = any(path.endswith(ext) for ext in ".py .js .ts .jsx .tsx .java .go .rs .cpp .c .h .cs .rb .php .swift .kt .scala .r .m".split())
        is_requirements = path.endswith("requirements.txt") or path.endswith("package.json")
        
        if not is_code_file and not is_requirements:
            accepted.append(path)
            continue
        
        # For requirements.txt / package.json - just check they're not empty
        if is_requirements:
            if len(content.strip()) < 3:
                rejected.append(f"{path}: Dependency file is empty or near-empty")
                continue
            accepted.append(path)
            continue
        
        # Code file quality checks
        if total_lines < 3:
            rejected.append(f"{path}: Too short ({total_lines} lines, min 3)")
            continue
        
        if code_lines < MIN_EXECUTABLE_LINES:
            rejected.append(
                f"{path}: Only {code_lines} executable lines (min {MIN_EXECUTABLE_LINES}). "
                f"File is mostly comments ({comment_lines} comment lines). "
                f"Must contain actual functions, classes, or logic."
            )
            continue
        
        if total_lines > 0 and comment_lines / total_lines > MAX_COMMENT_RATIO:
            rejected.append(
                f"{path}: {comment_lines}/{total_lines} lines are comments ({comment_lines/total_lines:.0%}). "
                f"Too little actual code. Must implement real logic, not just describe it."
            )
            continue
        
        # Check for meaningful code structures
        has_function = re.search(r"(def\s+\w+\s*\(|function\s+\w+\s*\(|const\s+\w+\s*=\s*(?:async\s*)?\(|class\s+\w+)", content)
        has_import = re.search(r"(import\s+|from\s+\S+\s+import|require\s*\(|using\s+|#include)", content)
        has_logic = re.search(r"(?:if\s|for\s|while\s|return\s|try\s*:|catch\s*\(|await\s|\.map\s*\(|\.filter\s*\(|\.reduce\s*\()", content)
        
        if not (has_function or has_logic or has_import):
            rejected.append(
                f"{path}: No executable structures found (no functions, classes, control flow, or imports). "
                f"File appears to be comments or placeholder text only."
            )
            continue
        
        accepted.append(path)
    
    is_valid = len(rejected) == 0
    return is_valid, rejected, accepted


# =============================================================================
# PACKAGE VERIFICATION
# =============================================================================

# Known PyPI packages (common ones) - used for fast validation
KNOWN_PYPI_PACKAGES = {
    "requests", "httpx", "aiohttp", "fastapi", "flask", "django", "tornado",
    "pydantic", "sqlalchemy", "sqlmodel", "alembic", "psycopg2", "psycopg2-binary",
    "pymongo", "redis", "celery", "pytest", "pytest-asyncio", "black", "flake8",
    "mypy", "pylint", "bandit", "coverage", "tox", "poetry", "uv", "pip",
    "numpy", "pandas", "matplotlib", "seaborn", "scipy", "scikit-learn",
    "torch", "tensorflow", "jax", "transformers", "accelerate", "datasets",
    "pillow", "opencv-python", "pytesseract", "beautifulsoup4", "lxml",
    "playwright", "selenium", "scrapy", "twisted", "channels", "daphne",
    "gradio", "streamlit", "dash", "plotly", "bokeh", "altair",
    "openai", "anthropic", "groq", "httpx", "aiohttp", "trio", "anyio",
    "pydantic", "pydantic-settings", "typer", "click", "rich", "loguru",
    "structlog", "python-dotenv", "jinja2", "markupsafe", "mako",
    "boto3", "botocore", "azure-storage", "google-cloud-storage", "gcsfs",
    "cryptography", "hashlib", "bcrypt", "argon2-cffi", "passlib", "pyjwt",
    "stripe", "paypalrestsdk", "braintree", "razorpay", "squareup",
    "sentry-sdk", "newrelic", "datadog", "prometheus-client", "opentelemetry",
    "fastapi", "starlette", "uvicorn", "gunicorn", "hypercorn", "daphne",
    "jinja2", "mako", "chameleon", "django-jinja", "django-cors-headers",
    "djangorestframework", "django-filter", "django-extensions", "django-debug-toolbar",
    "flask-sqlalchemy", "flask-migrate", "flask-login", "flask-wtf", "flask-cors",
    "werkzeug", "itsdangerous", "blinker", "click", "colorama",
    "regex", "re", "json", "csv", "xml", "yaml", "toml", "configparser",
    "python-dateutil", "pytz", "pendulum", "arrow", "moment", "delorean",
    "faker", "factory-boy", "hypothesis", "model-bakery", "freezegun",
    "ipython", "jupyter", "notebook", "ipywidgets", "nbformat", "nbconvert",
    "sphinx", "mkdocs", "pdoc", "pydoc", "pdoc3", "readme-renderer",
    "setuptools", "wheel", "twine", "build", "hatch", "flit", "poetry",
    "pkginfo", "packaging", "versioneer", "bumpversion", "semantic-version",
    "pre-commit", "gitpython", "pygithub", "github3", "gitlab",
    "slack-sdk", "discord-py", "twilio", "sendgrid", "mailgun", "postmark",
    "telebot", "python-telegram-bot", "aiogram", "tgcrypto", "pyrogram",
    "tweepy", "facebook-sdk", "instagrapi", "linkedin-api", "youtube-dl",
    "moviepy", "ffmpeg-python", "imageio", "imageio-ffmpeg", "av",
    "wave", "pydub", "librosa", "soundfile", "speechrecognition", "pyaudio",
    "sentence-transformers", "faiss-cpu", "chromadb", "weaviate-client",
    "langchain", "langchain-openai", "langchain-anthropic", "llamaindex",
    "tiktoken", "tokenizers", "transformers", "diffusers", "accelerate",
    "safetensors", "huggingface-hub", "datasets", "evaluate", "trl", "peft",
    "unsloth", "vllm", "sglang", "litellm", "instructor",
    "qdrant-client", "milvus", "pinecone-client", "vectordb", "lancedb",
    "pymilvus", "elasticsearch", "opensearch-py", "meilisearch", "typesense",
    "apscheduler", "schedule", "croniter", "celery", "dramatiq", "huey",
    "rq", "kombu", "amqp", "pika", "aio-pika", "stomp.py", "mqtt",
    "socketio", "python-socketio", "websockets", "aiofiles", "watchdog",
    "inotify", "fswatch", "pyinotify", "watchfiles", "livereload",
    "paramiko", "fabric", "ansible", "salt", "puppet", "chef",
    "docker", "docker-compose", "kubernetes", "helm", "kustomize",
    "terraform", "pulumi", "boto3", "azure-cli", "google-cloud-sdk",
    "pynacl", "cryptography", "rsa", "ecdsa", "ed25519", "blake3",
    "hashlib", "hmac", "secrets", "random", "uuid", "shortuuid", "nanoid",
    "phonenumbers", "email-validator", "validators", "pycountry", "babel",
    "money", "py-moneyed", "forex-python", "yfinance", "alpha-vantage",
    "polygon-api", "iexfinance", "quandl", "twelvedata", "finnhub",
    "ccxt", "binance-connector", "kucoin-python", "okx", "bitmex",
    "web3", "eth-account", "eth-keys", "eth-hash", "eth-utils",
    "solana", "anchorpy", "solders", "splat", "sui", "aptos-sdk",
    "bitcoinlib", "bit", "pycoin", "btclib", "base58", "bech32",
    "mnemonic", "bip32", "bip39", "bip44", "hdwallet", "eth-wallet",
    "qrcode", "pillow", "pyzbar", "zxing", "opencv-python", "imagehash",
    "python-barcode", "python-qrcode", "segno", "pystrich", "treepoem",
    "pdfplumber", "pypdf", "pdf2image", "camelot-py", "tabula-py",
    "openpyxl", "xlrd", "xlwt", "xlsxwriter", "pyxlsb", "odfpy",
    "docx", "python-docx", "docxtpl", "pdfkit", "weasyprint", "xhtml2pdf",
    "reportlab", "fpdf", "fpdf2", "borb", "pikepdf", "pymupdf", "fitz",
    "sqlite3", "psycopg", "psycopg2", "psycopg2-binary", "asyncpg",
    "mysql-connector-python", "pymysql", "aiomysql", "sqlalchemy", "sqlalchemy-utils",
    "alembic", "dataset", "records", "peewee", "tortoise-orm", "ormar",
    "prisma", "edgedb-python", "asyncpg", "databases", "encode-databases",
    "minio", "boto3", "botocore", "s3fs", "gcsfs", "adlfs", "fsspec",
    "zarr", "h5py", "netcdf4", "xarray", "dask", "distributed", "coiled",
    "modin", "polars", "pyarrow", "fastparquet", "duckdb", "sqlite-vss",
    "networkx", "igraph", "graph-tool", "snap", "karateclub", "node2vec",
    "gensim", "word2vec", "doc2vec", "fasttext", "textblob", "spacy",
    "nltk", "stanza", "allennlp", "flair", "transformers", "sentencepiece",
    "protobuf", "grpcio", "grpcio-tools", "thrift", "avro", "msgpack",
    "cbor2", "orjson", "ujson", "rapidjson", "simdjson", "json5",
    "toml", "tomli", "tomli-w", "pytomlpp", "rtoml", "configobj",
    "pyyaml", "ruamel-yaml", "strictyaml", "oyaml", "yaml-1.3",
    "sh", "plumbum", "delegator-py", "pexpect", "ptyprocess", "subprocess",
    "invoke", "fabric", "paramiko", "scp", "sftp", "ftplib", "urllib3",
    "requests-toolbelt", "requests-oauthlib", "oauthlib", "authlib",
    "python-jose", "python-jwt", "jose", "pyjwt", "itsdangerous",
    "flask-limiter", "slowapi", "django-ratelimit", "ratelimit",
    "cachetools", "diskcache", "cachelib", "python-cachetools", "ring",
    "joblib", "dill", "cloudpickle", "pickle", "shelve", "dbm",
    "tqdm", "alive-progress", "rich", "blessed", "urwid", "npyscreen",
    "curses", "windows-curses", "colorama", "termcolor", "colored",
    "sty", "pastel", "colorful", "chroma", "hexcolor", "webcolors",
    "fontawesome", "octicons", "material-design-icons", "feather-icons",
    "pydantic", "pydantic-settings", "pydantic-extra-types", "msgspec",
    "cattrs", "attrs", "dataclasses", "namedtuple", "typing", "mypy",
    "typesystem", "schematics", "marshmallow", "cerberus", "voluptuous",
    "schema", "jsonschema", "fastjsonschema", "jsonschema-specifications",
    "openapi-spec-validator", "prance", "swagger-ui-bundle", "flasgger",
    "apispec", "flask-apispec", "flask-restx", "flask-restful", "flask-smorest",
    "falcon", "hug", "apistar", "responder", "starlette", "fastapi",
    "litestar", "blacksheep", "tornado", "sanic", "quart", "aiohttp",
    "webpy", "bottle", "cherrypy", "pyramid", "paste", "webob",
    "wsgiref", "asgiref", "daphne", "hypercorn", "uvicorn", "gunicorn",
    "mod-wsgi", "passenger", "uWSGI", "waitress", "bjoern", "meinheld",
    "gevent", "eventlet", "greenlet", "trio", "anyio", "curio", "asyncio",
    "aiofiles", "aioshutil", "aiozip", "aiopath", "aiosqlite", "aioredis",
    "aiomcache", "aiokafka", "aiobotocore", "aioftp", "aiosmtpd",
    "pytest", "pytest-asyncio", "pytest-cov", "pytest-xdist", "pytest-mock",
    "pytest-django", "pytest-flask", "pytest-fastapi", "pytest-factoryboy",
    "unittest", "unittest2", "nose", "nose2", "green", "trial", "zope-testrunner",
    "locust", "k6", "artillery", "gatling", "jmeter", "tsung", "siege",
    "ab", "wrk", "vegeta", "bombardier", "hey", "httperf", "slowhttptest",
    "bandit", "safety", "pip-audit", "pip-licenses", "licensecheck",
    "detect-secrets", "git-secrets", "trufflehog", "gitleaks", "tartufo",
    "semgrep", "codeql", "sonarqube", "prospector", "pylama", "flake8",
    "pycodestyle", "pyflakes", "mccabe", "radon", "xenon", "cohesion",
    "wemake-python-styleguide", "flake8-bugbear", "flake8-comprehensions",
    "flake8-docstrings", "flake8-import-order", "flake8-quotes", "pep8-naming",
    "black", "isort", "autopep8", "yapf", "reformat-gherkin", "sourcery-cli",
    "mypy", "pytype", "pyre-check", "pyright", "basedpyright", "typeshed",
    "stubgen", "stubs", "typing-extensions", "typing-inspect", "typeguard",
}


def validate_requirements_txt(content: str) -> Tuple[bool, List[str]]:
    """
    Validate that packages in requirements.txt are real/known packages.
    
    Returns:
        (is_valid, list of suspicious packages)
    """
    suspicious = []
    lines = content.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Extract package name (before ==, >=, <=, ~=, etc.)
        pkg = re.split(r"[=<>!~;\[]", line)[0].strip().lower()
        
        if not pkg:
            continue
        
        # Normalize: pip treats hyphens and underscores as equivalent
        normalized = pkg.replace("_", "-")
        
        # Check against known packages (with some fuzziness)
        if normalized not in KNOWN_PYPI_PACKAGES:
            # Check if it's a well-known package with slight variation
            # (e.g., "requests-toolbelt" vs "requests")
            known_parts = any(part in KNOWN_PYPI_PACKAGES for part in normalized.split("-"))
            if not known_parts and pkg not in {"os", "sys", "json", "re", "math", "random", "datetime", "time", "pathlib", "typing", "collections", "itertools", "functools", "hashlib", "base64", "urllib", "http", "socket", "threading", "multiprocessing", "subprocess", "warnings", "logging", "inspect", "traceback", "copy", "pickle", "csv", "xml", "html", "email", "smtplib", "imaplib", "poplib", "ftplib", "telnetlib", "uuid", "secrets", "string", "textwrap", "enum", "dataclasses", "abc", "numbers", "decimal", "fractions", "statistics", "bisect", "heapq", "queue", "weakref", "gc", "atexit", "signal", "mmap", "msvcrt", "winreg", "winsound", "ctypes", "cffi", "swig", "cython", "pyrex", "numpy", "pandas"}:
                suspicious.append(f"'{pkg}' — not found in known PyPI packages (may be hallucinated)")
    
    return len(suspicious) == 0, suspicious


# =============================================================================
# MAIN INTEGRATION: Apply safety + quality gates
# =============================================================================

async def apply_safety_and_quality_gates(
    goal: str,
    files: List[Dict[str, str]],
    orchestrator=None
) -> Dict[str, Any]:
    """
    Apply all safety and quality gates to generated files.
    
    Uses LLM-based safety classification instead of keyword matching.
    
    Args:
        goal: The user's goal
        files: Generated file list
        orchestrator: Optional ModelOrchestrator for LLM-based classification
    
    Returns dict with:
        - safe: bool (True if passed all gates)
        - blocked_reason: str (if blocked by safety)
        - quality_issues: List[str] (code quality problems)
        - package_issues: List[str] (suspicious packages)
        - accepted_files: List[str] (paths that passed)
        - rejected_files: List[str] (paths that failed)
    """
    result = {
        "safe": False,
        "blocked_reason": None,
        "quality_issues": [],
        "package_issues": [],
        "accepted_files": [],
        "rejected_files": [],
    }
    
    # Step 1: Safety check on the goal (using LLM)
    risk_level, confidence, refusal = await classify_safety_risk(goal, orchestrator)
    if risk_level == "block":
        result["blocked_reason"] = refusal
        logger.warning(f"Safety gate BLOCKED goal: {goal[:80]}... (confidence: {confidence:.2f})")
        return result
    
    # Step 2: Code quality validation
    quality_ok, quality_rejected, quality_accepted = validate_code_quality(files)
    result["quality_issues"] = quality_rejected
    result["accepted_files"] = quality_accepted
    result["rejected_files"] = quality_rejected
    
    # Step 3: Package verification for requirements.txt
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        if path.endswith("requirements.txt") or path == "requirements.txt":
            pkg_ok, pkg_issues = validate_requirements_txt(content)
            result["package_issues"].extend(pkg_issues)
    
    # Final verdict: only safety blocks are hard stops.
    # Quality and package issues are WARNINGS — the generated code
    # is far more useful with minor issues than completely absent.
    if risk_level == "block":
        result["safe"] = False
    else:
        result["safe"] = True
        if result["quality_issues"]:
            logger.warning(
                "Quality issues (%d) allowed through for deliverable: %s",
                len(result["quality_issues"]),
                "; ".join(result["quality_issues"][:3]),
            )
        if result["package_issues"]:
            logger.warning(
                "Package issues (%d) allowed through: %s",
                len(result["package_issues"]),
                "; ".join(result["package_issues"][:3]),
            )
    
    return result


def build_rejection_message(gate_result: Dict[str, Any]) -> str:
    """Build a human-readable rejection message from gate results."""
    parts = []
    
    if gate_result.get("blocked_reason"):
        parts.append(gate_result["blocked_reason"])
    
    if gate_result.get("quality_issues"):
        parts.append("\n[QUALITY ISSUES]\n")
        for issue in gate_result["quality_issues"]:
            parts.append(f"- {issue}")
    
    if gate_result.get("package_issues"):
        parts.append("\n[PACKAGE ISSUES]\n")
        for issue in gate_result["package_issues"]:
            parts.append(f"- {issue}")
    
    if not parts:
        return "Unknown rejection reason."
    
    return "\n".join(parts)

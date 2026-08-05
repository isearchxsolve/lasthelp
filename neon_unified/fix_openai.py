with open("C:/Users/Admin/Downloads/neon_unified/generation_core.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the location to insert - right before "class GenAgent:"
old = """# =============================================================================
# Base agent
# =============================================================================

class GenAgent:"""

new = """# =============================================================================
# Base agent
# =============================================================================

# Safe import of openai for error handling
try:
    import openai
    OPENAI_ERRORS = (
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
        openai.RateLimitError,
        openai.APIStatusError,
    )
except ImportError:
    openai = None  # type: ignore
    OPENAI_ERRORS = (Exception,)


class GenAgent:"""

if old in content:
    content = content.replace(old, new)
    with open("C:/Users/Admin/Downloads/neon_unified/generation_core.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS: openai import and OPENAI_ERRORS added")
else:
    print("ERROR: Could not find insertion point")

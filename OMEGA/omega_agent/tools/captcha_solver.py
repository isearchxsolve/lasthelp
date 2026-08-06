"""Production-grade CAPTCHA Solver for OMEGA.

This module provides multi-modal CAPTCHA solving capabilities:
- OCR-based image CAPTCHA solving using Tesseract
- LLM-based text/logic CAPTCHA solving
- Behavioral bypass techniques (random mouse movements, scrolling)
- Rate limiting and retry logic with exponential backoff
- Proper error handling and logging
- Configuration-driven behavior

Architecture:
- All functions are async where applicable
- Multiple solving strategies with fallback chain
- Graceful degradation if strategies fail
- Comprehensive logging for audit trail

Install requirements (add to requirements.txt):
    pytesseract>=0.3.10
    Pillow>=10.0.0

After pip install, ensure Tesseract OCR is installed on your system:
    - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
    - macOS: brew install tesseract
    - Linux: sudo apt-get install tesseract-ocr
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import random
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("omega_agent.tools.captcha_solver")

# ── Lazy imports ─────────────────────────────────────────────────────────────

def _get_pytesseract():
    try:
        import pytesseract
        return pytesseract
    except ImportError:
        return None

def _get_pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


# ── CAPTCHA Solver Configuration ─────────────────────────────────────────────

CAPTCHA_CONFIG = {
    # Maximum number of retry attempts
    "max_retries": 3,
    
    # Base delay between retries (seconds)
    "retry_base_delay": 1.0,
    
    # Maximum delay between retries (seconds)
    "retry_max_delay": 10.0,
    
    # OCR configuration
    "ocr_config": "--psm 8 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    
    # Minimum confidence threshold for OCR results
    "ocr_min_confidence": 0.5,
    
    # Minimum length for valid CAPTCHA answer
    "min_answer_length": 3,
    
    # Maximum length for valid CAPTCHA answer
    "max_answer_length": 10,
    
    # Behavioral bypass settings
    "behavioral_enabled": True,
    "behavioral_mouse_moves": 3,
    "behavioral_scroll_attempts": 1,
}


# ── CAPTCHA Solver Class ─────────────────────────────────────────────────────

class CaptchaSolver:
    """Production-grade CAPTCHA solver with multi-modal approach."""
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm_call_fn: Optional[Callable] = None,
    ):
        """Initialize CAPTCHA solver.
        
        Args:
            config: Optional configuration overrides
            llm_call_fn: Optional LLM call function for text CAPTCHA solving
                        Signature: llm_call_fn(messages, persona=None, override_max_tokens=None) -> str
        """
        self.config = {**CAPTCHA_CONFIG, **(config or {})}
        self.llm_call_fn = llm_call_fn
        self._pytesseract = _get_pytesseract()
        self._pil = _get_pil()
        self._stats = {
            "total_attempts": 0,
            "ocr_success": 0,
            "llm_success": 0,
            "behavioral_success": 0,
            "failures": 0,
        }
        
        if not self._pytesseract:
            logger.warning("pytesseract not installed - OCR CAPTCHA solving disabled")
        if not self._pil:
            logger.warning("PIL not installed - image processing disabled")
        if not self.llm_call_fn:
            logger.warning("No LLM call function provided - text CAPTCHA solving disabled")
    
    async def solve_image_captcha(
        self,
        image_path_or_url: str,
        use_ocr: bool = True,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """Solve an image CAPTCHA using OCR and/or LLM.
        
        Args:
            image_path_or_url: Path to image file or URL
            use_ocr: Whether to attempt OCR-based solving
            use_llm: Whether to attempt LLM-based solving
            
        Returns:
            Dict with success status, method used, and answer
        """
        self._stats["total_attempts"] += 1
        
        try:
            # Load image
            img = await self._load_image(image_path_or_url)
            if not img:
                return {
                    "success": False,
                    "error": "Failed to load image",
                    "method": "none",
                }
            
            # Try OCR first
            if use_ocr and self._pytesseract and self._pil:
                ocr_result = await self._solve_with_ocr(img)
                if ocr_result["success"]:
                    self._stats["ocr_success"] += 1
                    logger.info("CAPTCHA solved via OCR: %s", ocr_result["answer"])
                    return ocr_result
            
            # Try LLM fallback
            if use_llm and self.llm_call_fn:
                llm_result = await self._solve_with_llm(img)
                if llm_result["success"]:
                    self._stats["llm_success"] += 1
                    logger.info("CAPTCHA solved via LLM: %s", llm_result["answer"])
                    return llm_result
            
            # All methods failed
            self._stats["failures"] += 1
            return {
                "success": False,
                "error": "All solving methods failed",
                "method": "none",
            }
            
        except Exception as e:
            self._stats["failures"] += 1
            logger.error("Image CAPTCHA solving failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "none",
            }
    
    async def solve_text_captcha(
        self,
        question: str,
    ) -> Dict[str, Any]:
        """Solve a text/logic CAPTCHA using LLM.
        
        Args:
            question: CAPTCHA question or puzzle text
            
        Returns:
            Dict with success status, method used, and answer
        """
        self._stats["total_attempts"] += 1
        
        if not self.llm_call_fn:
            return {
                "success": False,
                "error": "LLM call function not provided",
                "method": "none",
            }
        
        try:
            prompt = (
                "Solve this CAPTCHA/logic puzzle. Reply with ONLY the answer, "
                "no explanations or extra text.\n\n"
                f"Question: {question}"
            )
            
            answer = await self._call_llm_async(prompt, max_tokens=100)
            
            if answer and len(answer.strip()) >= self.config["min_answer_length"]:
                self._stats["llm_success"] += 1
                logger.info("Text CAPTCHA solved: %s -> %s", question[:50], answer.strip())
                return {
                    "success": True,
                    "method": "llm",
                    "answer": answer.strip(),
                }
            
            self._stats["failures"] += 1
            return {
                "success": False,
                "error": "Invalid answer format",
                "method": "llm",
            }
            
        except Exception as e:
            self._stats["failures"] += 1
            logger.error("Text CAPTCHA solving failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "llm",
            }
    
    async def bypass_behavioral(self, page) -> Dict[str, Any]:
        """Perform behavioral bypass techniques on a Playwright page.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dict with success status and method used
        """
        self._stats["total_attempts"] += 1
        
        if not self.config["behavioral_enabled"]:
            return {
                "success": False,
                "error": "Behavioral bypass disabled in config",
                "method": "behavioral",
            }
        
        try:
            # Random mouse movements
            for _ in range(self.config["behavioral_mouse_moves"]):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                await page.mouse.move(x, y)
                await page.wait_for_timeout(random.randint(200, 800))
            
            # Random scroll
            for _ in range(self.config["behavioral_scroll_attempts"]):
                scroll_amount = random.randint(0, 300)
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                await page.wait_for_timeout(random.randint(300, 1000))
            
            self._stats["behavioral_success"] += 1
            logger.info("Behavioral bypass completed")
            return {
                "success": True,
                "method": "behavioral",
            }
            
        except Exception as e:
            self._stats["failures"] += 1
            logger.error("Behavioral bypass failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "behavioral",
            }
    
    async def solve_with_retry(
        self,
        solve_fn: Callable,
        *args,
        max_retries: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a CAPTCHA solving function with retry logic.
        
        Args:
            solve_fn: Async function to execute
            *args: Arguments to pass to solve_fn
            max_retries: Optional override for max retries
            **kwargs: Keyword arguments to pass to solve_fn
            
        Returns:
            Dict with success status and result
        """
        max_attempts = max_retries or self.config["max_retries"]
        
        for attempt in range(max_attempts):
            result = await solve_fn(*args, **kwargs)
            
            if result.get("success"):
                return result
            
            # Calculate delay with exponential backoff
            if attempt < max_attempts - 1:
                delay = min(
                    self.config["retry_base_delay"] * (2 ** attempt),
                    self.config["retry_max_delay"],
                )
                logger.info(
                    "CAPTCHA solve attempt %d failed, retrying in %.1fs",
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get CAPTCHA solver statistics.
        
        Returns:
            Dict with solving statistics
        """
        total = self._stats["total_attempts"]
        success_rate = (
            (self._stats["ocr_success"] + self._stats["llm_success"] + self._stats["behavioral_success"]) / total
            if total > 0
            else 0.0
        )
        
        return {
            **self._stats,
            "success_rate": round(success_rate * 100, 2),
        }
    
    def reset_stats(self) -> None:
        """Reset CAPTCHA solver statistics."""
        self._stats = {
            "total_attempts": 0,
            "ocr_success": 0,
            "llm_success": 0,
            "behavioral_success": 0,
            "failures": 0,
        }
    
    # ── Private Helper Methods ─────────────────────────────────────────────
    
    async def _load_image(self, image_path_or_url: str) -> Optional[Any]:
        """Load image from path or URL.
        
        Args:
            image_path_or_url: Path to image file or URL
            
        Returns:
            PIL Image object or None
        """
        if not self._pil:
            return None
        
        try:
            if image_path_or_url.startswith("http"):
                # Load from URL
                import aiohttp
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_path_or_url, timeout=15) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            return self._pil.Image.open(io.BytesIO(image_data))
                return None
            else:
                # Load from file path
                return self._pil.Image.open(image_path_or_url)
        except Exception as e:
            logger.error("Failed to load image from %s: %s", image_path_or_url, e)
            return None
    
    async def _solve_with_ocr(self, img: Any) -> Dict[str, Any]:
        """Solve CAPTCHA using OCR.
        
        Args:
            img: PIL Image object
            
        Returns:
            Dict with success status and answer
        """
        try:
            text = self._pytesseract.image_to_string(
                img,
                config=self.config["ocr_config"],
            )
            
            # Clean the text
            text = re.sub(r"[^\w]", "", text).strip()
            
            # Validate answer
            if (
                len(text) >= self.config["min_answer_length"]
                and len(text) <= self.config["max_answer_length"]
            ):
                return {
                    "success": True,
                    "method": "ocr",
                    "answer": text,
                }
            
            return {
                "success": False,
                "error": f"Invalid answer length: {len(text)}",
                "method": "ocr",
            }
            
        except Exception as e:
            logger.error("OCR solving failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "ocr",
            }
    
    async def _solve_with_llm(self, img: Any) -> Dict[str, Any]:
        """Solve CAPTCHA using LLM (VLM fallback).
        
        Args:
            img: PIL Image object
            
        Returns:
            Dict with success status and answer
        """
        try:
            # Convert image to base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            b64 = base64.b64encode(buffer.getvalue()).decode()
            
            # Note: This requires a multimodal LLM
            # For now, return error as VLM is not configured
            return {
                "success": False,
                "error": "VLM not available - requires multimodal model configuration",
                "method": "llm",
            }
            
        except Exception as e:
            logger.error("LLM solving failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "method": "llm",
            }
    
    async def _call_llm_async(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Call LLM asynchronously.
        
        Args:
            prompt: Prompt to send to LLM
            max_tokens: Optional max tokens override
            
        Returns:
            LLM response or None
        """
        if not self.llm_call_fn:
            return None
        
        try:
            # If llm_call_fn is async, await it
            if asyncio.iscoroutinefunction(self.llm_call_fn):
                return await self.llm_call_fn(
                    [{"role": "user", "content": prompt}],
                    override_max_tokens=max_tokens,
                )
            else:
                # If it's sync, run in executor
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self.llm_call_fn(
                        [{"role": "user", "content": prompt}],
                        override_max_tokens=max_tokens,
                    ),
                )
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return None


# ── Convenience Functions ─────────────────────────────────────────────────────

async def solve_captcha(
    captcha_type: str,
    data: Any,
    llm_call_fn: Optional[Callable] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function to solve a CAPTCHA.
    
    Args:
        captcha_type: Type of CAPTCHA ('image', 'text', 'behavioral')
        data: CAPTCHA data (image path/URL for image, question for text, page for behavioral)
        llm_call_fn: Optional LLM call function
        config: Optional configuration overrides
        
    Returns:
        Dict with success status and result
    """
    solver = CaptchaSolver(config=config, llm_call_fn=llm_call_fn)
    
    if captcha_type == "image":
        return await solver.solve_image_captcha(data)
    elif captcha_type == "text":
        return await solver.solve_text_captcha(data)
    elif captcha_type == "behavioral":
        return await solver.bypass_behavioral(data)
    else:
        return {
            "success": False,
            "error": f"Unknown CAPTCHA type: {captcha_type}",
        }


# ── Registration Helper ───────────────────────────────────────────────────────

def register_captcha_solver_tools(registry, llm_call_fn: Optional[Callable] = None) -> None:
    """Register CAPTCHA solver configuration with the tool registry.
    
    Args:
        registry: Tool registry instance
        llm_call_fn: Optional LLM call function for text CAPTCHA solving
    """
    # Store CAPTCHA solver configuration in registry for use by browser tools
    if not hasattr(registry, '_captcha_config'):
        registry._captcha_config = {
            'enabled': True,
            'config': CAPTCHA_CONFIG,
            'llm_call_fn': llm_call_fn,
        }
    
    logger.info("CAPTCHA solver configuration registered")

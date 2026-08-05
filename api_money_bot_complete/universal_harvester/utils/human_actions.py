"""Human-like interactions to evade bot detection."""
import random
import time
from playwright.sync_api import Page


def human_delay(min_ms: float = 300, max_ms: float = 1200) -> None:
    """Sleep for a random duration to mimic human hesitation."""
    delay = random.uniform(min_ms, max_ms) / 1000.0
    time.sleep(delay)


def human_type(page: Page, selector: str, text: str, mistake_rate: float = 0.02) -> None:
    """Type text like a human: occasional pauses, rare mistakes, backspaces."""
    el = page.query_selector(selector)
    if not el:
        raise ValueError(f"Element not found: {selector}")

    el.click()
    human_delay(100, 400)

    for char in text:
        # Occasional typo
        if random.random() < mistake_rate and char.isalpha():
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            el.type(wrong_char, delay=random.randint(30, 80))
            human_delay(100, 300)
            el.type("Backspace", delay=random.randint(30, 80))
            human_delay(100, 300)

        el.type(char, delay=random.randint(30, 120))

        # Random pause between words
        if char == ' ':
            human_delay(150, 500)
        elif random.random() < 0.05:
            human_delay(200, 600)

    human_delay(200, 500)


def human_click(page: Page, selector: str) -> None:
    """Click with a slight delay and possible pre-hover."""
    el = page.query_selector(selector)
    if not el:
        raise ValueError(f"Element not found: {selector}")

    # Sometimes hover first
    if random.random() < 0.3:
        el.hover()
        human_delay(200, 600)

    el.click()
    human_delay(300, 800)


def scroll_like_human(page: Page, amount: int = 500) -> None:
    """Scroll in small random increments."""
    steps = random.randint(3, 8)
    step_size = amount // steps
    for _ in range(steps):
        page.mouse.wheel(0, step_size + random.randint(-20, 20))
        human_delay(100, 400)


def random_mouse_wander(page: Page, duration: float = 1.5) -> None:
    """Move mouse around the page randomly before interacting."""
    viewport = page.viewport_size
    if not viewport:
        return

    start_x, start_y = random.randint(100, viewport["width"] - 100), random.randint(100, viewport["height"] - 100)
    page.mouse.move(start_x, start_y)

    end_time = time.time() + duration
    while time.time() < end_time:
        x = random.randint(50, viewport["width"] - 50)
        y = random.randint(50, viewport["height"] - 50)
        page.mouse.move(x, y)
        human_delay(200, 600)

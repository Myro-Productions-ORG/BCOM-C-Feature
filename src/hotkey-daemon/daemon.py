"""Hotkey daemon — intercepts Meta glasses tap (media play/pause) and toggles Bob.

macOS requirement: grant Accessibility permission to the terminal running this.
System Preferences → Privacy & Security → Accessibility → add Terminal (or iTerm2).
"""

import logging
import sys
import httpx
from pynput import keyboard

PROCESS_MANAGER_URL = "http://localhost:7766"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _toggle():
    try:
        httpx.post(f"{PROCESS_MANAGER_URL}/api/toggle-active", timeout=2.0)
        logger.info("Tap detected — toggle sent to Bob")
    except Exception as e:
        logger.warning("Could not reach process manager: %s", e)


def on_press(key):
    if key == keyboard.Key.media_play_pause:
        _toggle()


if __name__ == "__main__":
    logger.info("Hotkey daemon ready — waiting for Meta glasses tap (play/pause)")
    logger.info("If nothing happens: System Prefs → Privacy → Accessibility → add this terminal")

    with keyboard.Listener(on_press=on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            logger.info("Hotkey daemon stopped.")
            sys.exit(0)

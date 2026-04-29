import asyncio
import platform
import re
import time
from typing import Optional

import keyboard
import pyclip

from common.logger import setup_logger
from config.settings import ClientConfig

logger = setup_logger("output")

_typing_lock = asyncio.Lock()


def _is_chinese(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf"


def _split_text_segments(text: str) -> list:
    segments = []
    current = ""
    current_is_cjk = None

    for char in text:
        is_cjk = _is_chinese(char)
        if current_is_cjk is None:
            current_is_cjk = is_cjk
            current = char
        elif is_cjk == current_is_cjk:
            current += char
        else:
            segments.append((current_is_cjk, current))
            current = char
            current_is_cjk = is_cjk

    if current:
        segments.append((current_is_cjk, current))

    return segments


async def _verify_clipboard(expected_text: str, config: ClientConfig) -> bool:
    if not config.clipboard_verify:
        await asyncio.sleep(config.paste_delay)
        return True

    elapsed = 0.0
    while elapsed < config.clipboard_verify_timeout:
        try:
            actual = pyclip.paste().decode("utf-8")
            if actual == expected_text:
                return True
        except Exception:
            pass
        await asyncio.sleep(config.clipboard_verify_interval)
        elapsed += config.clipboard_verify_interval

    return False


async def _clipboard_type(text: str, config: ClientConfig):
    try:
        temp = pyclip.paste().decode("utf-8")
    except Exception:
        temp = ""

    pyclip.copy(text)

    verified = await _verify_clipboard(text, config)
    if not verified:
        pyclip.copy(text)
        await asyncio.sleep(config.paste_delay)

    if platform.system() == "Darwin":
        keyboard.press(55)
        keyboard.press(9)
        keyboard.release(55)
        keyboard.release(9)
    else:
        keyboard.send("ctrl + v")

    if config.restore_clipboard:
        await asyncio.sleep(config.restore_delay)
        try:
            pyclip.copy(temp)
        except Exception:
            pass


async def _keyboard_type(text: str, config: ClientConfig):
    for char in text:
        if _is_chinese(char):
            try:
                pyclip.copy(char)
                if platform.system() == "Darwin":
                    keyboard.press(55)
                    keyboard.press(9)
                    keyboard.release(55)
                    keyboard.release(9)
                else:
                    keyboard.send("ctrl + v")
                await asyncio.sleep(0.02)
            except Exception:
                keyboard.write(char)
                await asyncio.sleep(config.type_delay)
        else:
            keyboard.write(char)
            await asyncio.sleep(config.type_delay)


async def _hybrid_type(text: str, config: ClientConfig):
    segments = _split_text_segments(text)
    for is_cjk, segment in segments:
        if is_cjk:
            await _clipboard_type(segment, config)
        else:
            for char in segment:
                keyboard.write(char)
                await asyncio.sleep(config.type_delay)


async def type_result(text: str, config: ClientConfig):
    if not text:
        return

    async with _typing_lock:
        mode = config.output_mode

        if mode == "clipboard":
            await _clipboard_type(text, config)
        elif mode == "keyboard":
            await _keyboard_type(text, config)
        elif mode == "hybrid":
            await _hybrid_type(text, config)
        else:
            await _clipboard_type(text, config)

    logger.info(f"Output ({mode}): {text[:50]}...")

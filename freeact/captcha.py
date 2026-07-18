"""Free CAPTCHA solver — unique multi-strategy approach.

Strategy (tried in order):
1. Audio CAPTCHA + speech recognition (reCAPTCHA v2) — most reliable free method
2. Image CAPTCHA + EasyOCR/Tesseract — for text-based CAPTCHAs
3. Mouse simulation + human-like delays — for behavioral checks
4. Frame/iframe detection — find CAPTCHA widgets on page
5. Checkbox click + timing — for "I'm not a robot" checkboxes
"""

import asyncio
import base64
import io
import os
import random
import tempfile
import time
from typing import Optional

from playwright.async_api import Page


def _human_delay(min_ms: int = 50, max_ms: int = 300):
    return random.uniform(min_ms, max_ms) / 1000


def _human_mouse_path(start_x: int, start_y: int, end_x: int, end_y: int) -> list[dict]:
    """Generate human-like mouse movement points with bezier curves."""
    steps = random.randint(20, 40)
    points = []
    for i in range(steps + 1):
        t = i / steps
        cp1_x = start_x + (end_x - start_x) * random.uniform(0.2, 0.4)
        cp1_y = start_y + random.uniform(-30, 30)
        cp2_x = start_x + (end_x - start_x) * random.uniform(0.6, 0.8)
        cp2_y = end_y + random.uniform(-30, 30)
        x = (1 - t) ** 3 * start_x + 3 * (1 - t) ** 2 * t * cp1_x + 3 * (1 - t) * t**2 * cp2_x + t**3 * end_x
        y = (1 - t) ** 3 * start_y + 3 * (1 - t) ** 2 * t * cp1_y + 3 * (1 - t) * t**2 * cp2_y + t**3 * end_y
        points.append({"x": round(x), "y": round(y)})
    return points


async def _click_human(page: Page, selector: str):
    """Click with human-like mouse movement."""
    box = await page.locator(selector).bounding_box()
    if not box:
        await page.click(selector)
        return

    start_x = random.randint(100, 500)
    start_y = random.randint(100, 400)
    end_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    end_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

    points = _human_mouse_path(start_x, start_y, end_x, end_y)

    await page.mouse.move(start_x, start_y)
    await asyncio.sleep(_human_delay(100, 300))

    for pt in points[1:-1]:
        await page.mouse.move(pt["x"], pt["y"])
        await asyncio.sleep(_human_delay(5, 20))

    await page.mouse.move(end_x, end_y)
    await asyncio.sleep(_human_delay(50, 200))
    await page.mouse.click(end_x, end_y)
    await asyncio.sleep(_human_delay(200, 500))


async def _solve_audio_captcha(page: Page) -> dict:
    """Solve audio CAPTCHA (reCAPTCHA v2 audio challenge)."""
    try:
        audio_btn = page.locator("#recaptcha-audio-button, button[title='Get an audio challenge']")
        if await audio_btn.count() > 0:
            await _click_human(page, "#recaptcha-audio-button, button[title='Get an audio challenge']")
            await asyncio.sleep(2)

        audio_src = page.locator("#audio-source, .rc-audiochallenge-tdownload-link")
        if await audio_src.count() > 0:
            audio_url = await audio_src.first.get_attribute("src") or await audio_src.first.get_attribute("href")
            if audio_url:
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.close()

                import urllib.request
                urllib.request.urlretrieve(audio_url, tmp.name)

                try:
                    import speech_recognition as sr
                    recognizer = sr.Recognizer()
                    with sr.AudioFile(tmp.name) as source:
                        audio = recognizer.record(source)
                    text = recognizer.recognize_google(audio)
                except ImportError:
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["whisper", tmp.name, "--model", "tiny", "--output_format", "txt", "--output_dir", tempfile.gettempdir()],
                            capture_output=True, timeout=30,
                        )
                        text = result.stdout.decode().strip()
                    except Exception:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                        return {"ok": False, "error": "Speech recognition not available (pip install SpeechRecognition)"}

                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass

                if text:
                    response_input = page.locator("#audio-response")
                    if await response_input.count() > 0:
                        await response_input.fill(text.strip())
                        await asyncio.sleep(0.5)
                        verify_btn = page.locator("#recaptcha-verify-button")
                        if await verify_btn.count() > 0:
                            await _click_human(page, "#recaptcha-verify-button")
                            await asyncio.sleep(2)

                    captcha_frame = page.frame_locator("iframe[title*='recaptcha'], iframe[src*='recaptcha'], iframe[src*='google.com/recaptcha']")
                    try:
                        frame_audio = captcha_frame.locator("#audio-response")
                        if await frame_audio.count() > 0:
                            await frame_audio.fill(text.strip())
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass

                    return {"ok": True, "solved": True, "method": "audio", "text": text.strip()}

        return {"ok": False, "solved": False, "error": "Audio CAPTCHA not found or couldn't extract audio"}

    except Exception as e:
        return {"ok": False, "solved": False, "error": f"Audio solver error: {e}"}


async def _solve_image_captcha(page: Page) -> dict:
    """Solve text-based image CAPTCHA using OCR."""
    try:
        captcha_img = page.locator("img[src*='captcha'], img[id*='captcha'], img[class*='captcha'], .captcha img, #captcha-img, img[alt*='captcha']")
        if await captcha_img.count() == 0:
            captcha_img = page.locator("img").filter(has=page.locator("[src*='captcha']"))

        if await captcha_img.count() == 0:
            return {"ok": False, "solved": False, "error": "No CAPTCHA image found"}

        img = captcha_img.first
        screenshot_bytes = await img.screenshot()
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(screenshot_bytes)
        tmp.close()

        text = None
        try:
            import pytesseract
            from PIL import Image
            pil_img = Image.open(tmp.name)
            text = pytesseract.image_to_string(pil_img, config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789").strip()
        except ImportError:
            try:
                import easyocr
                reader = easyocr.Reader(["en"], gpu=False)
                result = reader.readtext(tmp.name)
                text = "".join([r[1] for r in result]).strip()
            except ImportError:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                return {"ok": False, "error": "OCR not available (pip install pytesseract or easyocr)"}

        try:
            os.unlink(tmp.name)
        except Exception:
            pass

        if text and len(text) >= 3:
            captcha_input = page.locator("input[id*='captcha'], input[name*='captcha'], input[placeholder*='captcha']")
            if await captcha_input.count() > 0:
                await captcha_input.first.fill(text)
                await asyncio.sleep(0.3)
                return {"ok": True, "solved": True, "method": "ocr", "text": text}

        return {"ok": False, "solved": False, "error": f"OCR produced: '{text}' — couldn't find input field"}

    except Exception as e:
        return {"ok": False, "solved": False, "error": f"Image solver error: {e}"}


async def _solve_recaptcha_v2(page: Page) -> dict:
    """Solve reCAPTCHA v2: find checkbox, click with human mouse, handle challenges."""
    try:
        checkbox = page.locator(".recaptcha-checkbox-border, #recaptcha-anchor, [role='presentation']").first
        if await checkbox.count() > 0:
            await _click_human(page, ".recaptcha-checkbox-border, #recaptcha-anchor")
            await asyncio.sleep(random.uniform(2, 4))

        await asyncio.sleep(1)

        challenge_visible = False
        for selector in [
            "#rc-imageselect", ".rc-imageselect", ".rc-audiochallenge",
            "iframe[title*='recaptcha challenge']",
        ]:
            el = page.locator(selector)
            if await el.count() > 0:
                try:
                    if await el.is_visible():
                        challenge_visible = True
                        break
                except Exception:
                    pass

        if challenge_visible:
            audio_result = await _solve_audio_captcha(page)
            if audio_result.get("solved"):
                return audio_result

        checkbox_checked = await page.locator(".recaptcha-checkbox-checked, #recaptcha-anchor[aria-checked='true']").count()
        if checkbox_checked > 0:
            return {"ok": True, "solved": True, "method": "checkbox"}

        return {"ok": False, "solved": False, "error": "reCAPTCHA not solved"}

    except Exception as e:
        return {"ok": False, "solved": False, "error": f"reCAPTCHA error: {e}"}


async def _solve_hcaptcha(page: Page) -> dict:
    """Solve hCaptcha: find checkbox, click with human timing."""
    try:
        hcaptcha_frame = page.frame_locator("iframe[src*='hcaptcha'], iframe[src*='hcaptcha.com']")
        try:
            checkbox = hcaptcha_frame.locator("#checkbox")
            if await checkbox.count() > 0:
                box = await checkbox.bounding_box()
                if box:
                    await page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    await asyncio.sleep(random.uniform(3, 6))

                    checked = await hcaptcha_frame.locator("#checkbox[aria-checked='true']").count()
                    if checked > 0:
                        return {"ok": True, "solved": True, "method": "hcaptcha"}
        except Exception:
            pass

        return {"ok": False, "solved": False, "error": "hCaptcha not solved"}

    except Exception as e:
        return {"ok": False, "solved": False, "error": f"hCaptcha error: {e}"}


async def _solve_turnstile(page: Page) -> dict:
    """Solve Cloudflare Turnstile: wait for auto-resolution with human-like behavior."""
    try:
        turnstile_frame = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
        try:
            checkbox = turnstile_frame.locator("input[type='checkbox'], .cb-i")
            if await checkbox.count() > 0:
                box = await checkbox.bounding_box()
                if box:
                    await page.mouse.move(
                        box["x"] + box["height"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    await asyncio.sleep(_human_delay(200, 600))
                    await page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
        except Exception:
            pass

        for _ in range(15):
            await asyncio.sleep(1)
            try:
                checked = await turnstile_frame.locator("[aria-checked='true'], .cb-i[data-cb-token]").count()
                if checked > 0:
                    return {"ok": True, "solved": True, "method": "turnstile"}
            except Exception:
                pass

        return {"ok": False, "solved": False, "error": "Turnstile timeout"}

    except Exception as e:
        return {"ok": False, "solved": False, "error": f"Turnstile error: {e}"}


async def solve_captcha_on_page(page: Page) -> dict:
    """Main CAPTCHA solver — tries all strategies in order."""
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(1)

    content = await page.content().lower()

    if "recaptcha" in content or "g-recaptcha" in content:
        result = await _solve_recaptcha_v2(page)
        if result.get("solved"):
            return result

    if "hcaptcha" in content or "data-hcaptcha" in content:
        result = await _solve_hcaptcha(page)
        if result.get("solved"):
            return result

    if "turnstile" in content or "challenges.cloudflare.com" in content:
        result = await _solve_turnstile(page)
        if result.get("solved"):
            return result

    img_result = await _solve_image_captcha(page)
    if img_result.get("solved"):
        return img_result

    return {"ok": True, "solved": False, "error": "No CAPTCHA detected or couldn't solve any type. Try remote-assist."}

"""Skill: chatgpt-register — Automated ChatGPT registration via temp email."""

import time
import sys

try:
    from freeact.daemon import send_daemon_command, is_daemon_running
except ImportError:
    print("Error: freeact not installed")
    sys.exit(1)

S = "live"


def cmd(path, body=None):
    b = body or {}
    b["session"] = S
    return send_daemon_command(path, b)


def ok(r):
    return r.get("ok", False)


def nav(url):
    return ok(cmd("/cmd/navigate", {"url": url}))


def get_email():
    print("[1/6] Getting temp email...")
    if not nav("https://emailtick.com/ru"):
        return None
    time.sleep(3)
    r = cmd("/cmd/eval", {"js": "document.querySelector('input[name=mailbox]')?.value||''"})
    e = r.get("result", "").strip()
    print("  Email:", e)
    return e or None


def signup(email):
    print("[2/6] Opening ChatGPT...")
    if not nav("https://chatgpt.com/auth/login"):
        return False
    time.sleep(4)

    print("[3/6] Entering email...")
    js = "(()=>{for(let el of document.querySelectorAll('input')){if(el.offsetParent!==null&&(el.type==='email'||el.type==='text')){el.value='" + email + "';el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return 'done';}}return 'not found';})()"
    r = cmd("/cmd/eval", {"js": js})
    if not ok(r):
        print("  ERROR:", r.get("error"))
    time.sleep(2)

    print("[4/6] Clicking continue...")
    js2 = "(()=>{for(let b of document.querySelectorAll('button')){let t=b.textContent.toLowerCase();if((t.includes('continue')||t.includes('sign')||t.includes('login')||t.includes('next'))&&b.offsetParent!==null){b.click();return b.textContent.trim();}}return 'not found';})()"
    r = cmd("/cmd/eval", {"js": js2})
    print("  Clicked:", r.get("result", "?"))
    time.sleep(4)
    return True


def get_code():
    print("[5/6] Checking email for code...")
    if not nav("https://emailtick.com/ru"):
        return None
    time.sleep(3)
    r = cmd("/cmd/eval", {"js": "(()=>{for(let tr of document.querySelectorAll('tr')){let m=tr.textContent.match(/\\b(\\d{4,8})\\b/);if(m)return m[1];}return '';})()"})
    code = r.get("result", "").strip()
    print("  Code:", code or "not found")
    return code or None


def enter_code(code):
    print("[6/6] Entering code", code, "...")
    nav("https://chatgpt.com")
    time.sleep(3)
    js = "(()=>{for(let el of document.querySelectorAll('input')){if(el.offsetParent!==null&&(el.type==='text'||el.type==='tel')){el.value='" + code + "';el.dispatchEvent(new Event('input',{bubbles:true}));return 'done';}}return 'not found';})()"
    cmd("/cmd/eval", {"js": js})
    time.sleep(2)
    print("  Code entered")
    return True


def run():
    if not is_daemon_running():
        print("Daemon not running. Start: freeact daemon")
        return False
    email = get_email()
    if email and signup(email):
        code = get_code()
        if code:
            enter_code(code)
    print("\nDone. Manual steps may remain (password/CAPTCHA).")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)

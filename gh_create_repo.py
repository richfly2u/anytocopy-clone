"""
GitHub repo creation via CDP (Windows Python + CentBrowser)
Creates a public repo 'daily-dashboard' on GitHub
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket
import json
import urllib.request
import urllib.parse
import time

CDP_PORT = 9223
WS_TIMEOUT = 30

def send_cdp(ws, method, params=None, timeout=15):
    """Send CDP command and wait for result with timeout"""
    msg_id = int(time.time() * 1000) % 1000000
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(1.0)
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as e:
            print(f"[WS ERROR] {e}")
            return None
        
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError:
            continue
        
        if resp.get("id") == msg_id:
            return resp
    print(f"[TIMEOUT] Command {method} (id={msg_id}) timed out after {timeout}s")
    return None

def evaluate(ws, expr, timeout=10):
    """Evaluate JavaScript in page context"""
    result = send_cdp(ws, "Runtime.evaluate", {
        "expression": expr,
        "returnByValue": True,
        "awaitPromise": True
    }, timeout=timeout)
    if result is None:
        return None
    exception = result.get("result", {}).get("exceptionDetails")
    if exception:
        print(f"[JS ERROR] {exception.get('text', str(exception))}")
        return None
    return result.get("result", {}).get("result", {}).get("value")

def click_element(ws, selector):
    """Click an element by CSS selector"""
    # Find element position via JS
    pos = evaluate(ws, f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {{ x: rect.left + rect.width/2, y: rect.top + rect.height/2 }};
        }})()
    """)
    if not pos:
        print(f"[ERROR] Element not found: {selector}")
        return False
    
    x, y = pos["x"], pos["y"]
    send_cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x, "y": y,
        "button": "left", "clickCount": 1
    })
    time.sleep(0.1)
    send_cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": x, "y": y,
        "button": "left", "clickCount": 1
    })
    return True

def type_text(ws, text):
    """Type text into focused element"""
    evaluate(ws, f"""
        document.activeElement.value = '';
        document.activeElement.value = {json.dumps(text)};
        document.activeElement.dispatchEvent(new Event('input', {{bubbles: true}}));
        document.activeElement.dispatchEvent(new Event('change', {{bubbles: true}}));
    """)

def wait_for_page(ws, timeout=30):
    """Wait for page to finish loading"""
    start = time.time()
    while time.time() - start < timeout:
        state = evaluate(ws, "document.readyState", timeout=5)
        if state == "complete":
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False

def create_tab(url):
    """Create a new tab via CDP REST API (PUT /json/new)"""
    req = urllib.request.Request(
        f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}",
        method="PUT"
    )
    resp = urllib.request.urlopen(req, timeout=10)
    tab = json.loads(resp.read())
    return tab["id"]

def connect_page(tab_id):
    """Connect to page WebSocket"""
    ws = websocket.create_connection(
        f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}",
        timeout=WS_TIMEOUT,
        enable_multithread=False
    )
    return ws

def main():
    print("=" * 60)
    print("GitHub Repo Automation via CDP")
    print("=" * 60)
    
    # Create a new tab to GitHub
    print("[1/8] Opening GitHub...")
    tab_id = create_tab("https://github.com")
    page_ws = connect_page(tab_id)
    print(f"   Tab ID: {tab_id}")
    
    # Wait for load
    print("[2/8] Waiting for page load...")
    wait_for_page(page_ws)
    
    # Get page title
    title = evaluate(page_ws, "document.title", timeout=10)
    print(f"   Page title: {title}")
    
    # Check login status
    print("[3/8] Checking login status...")
    time.sleep(2)
    
    login_check = evaluate(page_ws, """
        document.querySelector('meta[name="user-login"]')?.content ||
        document.querySelector('img.avatar')?.alt ||
        ''
    """, timeout=10)
    
    sign_in = evaluate(page_ws, """
        document.querySelector('a[href*="/login"], a[data-ga-click*="Sign in"]') !== null
    """, timeout=10)
    
    print(f"   Logged in as: {login_check}")
    print(f"   Login button visible: {sign_in}")
    
    if sign_in and not login_check:
        print("[!] NOT logged into GitHub. Please sign in manually in CentBrowser...")
        print("    Press Enter when done...")
        input()
        # Navigate to new repo page
        send_cdp(page_ws, "Page.navigate", {"url": "https://github.com/login"})
        wait_for_page(page_ws)
        time.sleep(3)
        
        # Check again
        send_cdp(page_ws, "Page.navigate", {"url": "https://github.com/new"})
        wait_for_page(page_ws)
        time.sleep(3)
    else:
        # Navigate to new repo page
        print("[4/8] Navigating to https://github.com/new...")
        send_cdp(page_ws, "Page.navigate", {"url": "https://github.com/new"})
        wait_for_page(page_ws)
        time.sleep(3)
    
    # Get current URL
    cur_url = evaluate(page_ws, "window.location.href", timeout=10)
    print(f"   Current URL: {cur_url}")
    
    if "/new" not in cur_url and "/login" not in cur_url:
        print("[!] Redirected. Let me try navigating again...")
        send_cdp(page_ws, "Page.navigate", {"url": "https://github.com/new"})
        wait_for_page(page_ws)
        time.sleep(3)
    
    # Fill repository name - new GitHub UI
    print("[5/8] Filling repository name...")
    
    # Debug: check what the form looks like
    body_html = evaluate(page_ws, "document.querySelector('main')?.innerText?.substring(0, 500)", timeout=10)
    print(f"   Page body text: {body_html}")
    
    # Use the React input ID with native value setter
    evaluate(page_ws, """
        const inp = document.querySelector('#repository-name-input');
        if (inp) { 
            inp.focus();
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(inp, 'daily-dashboard');
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
        }
    """, timeout=5)
    time.sleep(1)

    # Verify
    value = evaluate(page_ws, "document.querySelector('#repository-name-input')?.value", timeout=5)
    print(f"   Repo name: '{value}'")
    
    # Fill description
    print("[6/8] Filling description...")
    evaluate(page_ws, """
        // Find description field - it has name="Description"
        const desc = document.querySelector('[name="Description"], #_r_f_');
        if (desc) { 
            desc.focus();
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSetter.call(desc, 'Daily Dashboard PWA with Firestore sync');
            desc.dispatchEvent(new Event('input', { bubbles: true }));
            desc.dispatchEvent(new Event('change', { bubbles: true }));
        }
    """, timeout=5)
    time.sleep(1)
    
    # Ensure Public is selected
    print("[7/8] Ensuring Public...")
    evaluate(page_ws, """
        const radios = document.querySelectorAll('input[type="radio"][name*="visibility"], input[type="radio"][value="public"]');
        radios.forEach(r => { if(r.value === 'public' || r.id.includes('public')) { r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }});
        
        // Also try clicking the Public label
        document.querySelector('[for*="public"], label:has(input[value="public"])')?.click();
    """, timeout=5)
    time.sleep(1)
    
    # Uncheck auto-init
    evaluate(page_ws, """
        const auto = document.querySelector('#repository_auto_init');
        if (auto && auto.checked) { auto.click(); }
    """, timeout=5)
    time.sleep(1)
    
    # Click Create repository - find the submit button
    print("[8/8] Clicking Create repository...")
    
    # Debug: find buttons
    buttons = evaluate(page_ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
            text: b.innerText?.trim()?.substring(0, 30),
            disabled: b.disabled,
            type: b.type,
            classes: b.className?.substring(0, 50)
        })))
    """, timeout=10)
    print(f"   Buttons found: {buttons}")
    
    # Try clicking the Create repository button
    clicked = evaluate(page_ws, """
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const createBtn = btns.find(b => b.innerText.trim() === 'Create repository' && !b.disabled);
            if (createBtn) { createBtn.click(); return 'clicked: Create repository'; }
            // fallback: any submit button inside the form
            const form = document.querySelector('form');
            if (form) {
                const submit = form.querySelector('button[type="submit"]:not([disabled])');
                if (submit) { submit.click(); return 'clicked form submit'; }
            }
            return 'no Create repository button found';
        })()
    """, timeout=10)
    print(f"   Click result: {clicked}")
    
    time.sleep(5)
    wait_for_page(page_ws)
    
    # Get the repo URL
    current_url = evaluate(page_ws, "window.location.href", timeout=10)
    repo_title = evaluate(page_ws, "document.title", timeout=10)
    
    # Also get clone URL
    clone_url = evaluate(page_ws, """
        document.querySelector('input[aria-label*="clone"], input#empty-setup-clone-url, .clone-url')?.value ||
        window.location.href.replace('https://github.com/', 'https://github.com/').replace(/\\/$/, '') + '.git'
    """, timeout=10)
    
    print()
    print("=" * 60)
    print(f"✅ Repo URL: {current_url}")
    print(f"✅ Page title: {repo_title}")
    print(f"✅ Clone URL (guessed): {clone_url or current_url + '.git'}")
    print("=" * 60)
    
    page_ws.close()

if __name__ == "__main__":
    main()

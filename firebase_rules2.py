"""
Navigate to Firestore rules and update them
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223

def evaluate(ws, expr, timeout=10):
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": True
    }}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(1.0); raw = ws.recv()
        except websocket.WebSocketTimeoutException: continue
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError: continue
        if resp.get("id") == msg_id:
            exc = resp.get("result", {}).get("exceptionDetails")
            if exc: return None
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def wait_for_nav(ws, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        state = evaluate(ws, "document.readyState", timeout=5)
        if state == "complete":
            time.sleep(3)
            return True
        time.sleep(0.5)
    return False

def main():
    print("=" * 60)
    print("Firebase Console - Firestore Rules (v2)")
    print("=" * 60)
    
    # Go to Firestore directly
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    wait_for_nav(ws)
    time.sleep(5)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"URL: {url}")
    
    # Click the Rules tab
    print("[1/4] Clicking Rules tab...")
    clicked = evaluate(ws, """
        (() => {
            const links = document.querySelectorAll('a, span, div, li');
            for (const el of links) {
                if (el.innerText && el.innerText.trim() === 'Rules') {
                    el.click();
                    return 'clicked Rules tab';
                }
                if (el.getAttribute('role') === 'tab' && el.innerText.includes('Rules')) {
                    el.click();
                    return 'clicked Rules tab by role';
                }
            }
            return 'Rules tab not found';
        })()
    """)
    print(f"   {clicked}")
    time.sleep(5)
    
    url2 = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL after click: {url2}")
    
    # Try the rules tab by URL
    if "rules" not in url2:
        print("[!] Direct navigation to Rules...")
        evaluate(ws, "window.location.href = 'https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/rules'")
        time.sleep(5)
        wait_for_nav(ws)
        time.sleep(5)
    
    url3 = evaluate(ws, "window.location.href", timeout=10)
    print(f"   Final URL: {url3}")
    
    # Now look for the rules editor
    print("[2/4] Reading current rules...")
    text = evaluate(ws, "document.body.innerText?.substring(0, 3000)", timeout=10)
    print(f"   Page text: {text}")
    
    # Check for buttons on the rules page
    btns = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button, [role="button"], a')).map(el => ({
            text: (el.innerText || '').trim().substring(0, 40),
            aria: el.getAttribute('aria-label') || '',
            tag: el.tagName
        })).filter(b => b.text || b.aria))
    """, timeout=10)
    print(f"   Buttons: {btns[:2000]}")
    
    # Look for editor - monaco, codemirror, or textarea
    editors = evaluate(ws, """
        JSON.stringify({
            monaco: typeof monaco !== 'undefined',
            cm: document.querySelector('.CodeMirror') !== null,
            textarea: document.querySelector('textarea') !== null,
            ace: document.querySelector('.ace_editor') !== null,
            editorCount: document.querySelectorAll('[role="textbox"], .monaco-editor, .CodeMirror, textarea').length
        })
    """, timeout=10)
    print(f"   Editors: {editors}")
    
    # Check the full HTML for the rules section
    html = evaluate(ws, "document.querySelector('main, firebase-app, router-outlet')?.innerHTML?.substring(0, 5000)", timeout=10)
    print(f"\n--- HTML snippet ---\n{html}")
    
    ws.close()
    print("\n✅ Checked!")

if __name__ == "__main__":
    main()

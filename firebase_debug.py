"""
Debug: check what's on the rules page
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223

def cdp(ws, method, params=None, timeout=15):
    mid = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(0.5); raw = ws.recv()
        except: continue
        try:
            r = json.loads(raw)
        except: continue
        if r.get("id") == mid: return r
    return None

def js(ws, expr, timeout=15):
    r = cdp(ws, "Runtime.evaluate", {
        "expression": expr, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }, timeout)
    if r and "result" in r:
        ed = r["result"].get("exceptionDetails")
        if ed: return f"[ERR] {ed.get('text','')}"
        return r["result"].get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def main():
    print("=" * 60)
    print("Debug Rules Page")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/security/rules")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(10)
    
    print(f"URL: {js(ws, 'window.location.href')}")
    print(f"Title: {js(ws, 'document.title')}")
    
    # Check what's on the page
    text = js(ws, "document.body.innerText.substring(0, 3000)")
    print(f"\nPage text:\n{text}")
    
    # Check for editor elements
    editors = js(ws, """
        JSON.stringify({
            codemirror: document.querySelectorAll('.CodeMirror').length,
            monaco: document.querySelectorAll('.monaco-editor').length,
            textarea: document.querySelectorAll('textarea').length,
            textbox: document.querySelectorAll('[role="textbox"]').length,
            pre: document.querySelectorAll('pre').length,
            // Check if we're in the right view
            has_rules_text: document.body.innerText.includes('rules_version'),
            has_publish: document.body.innerText.includes('發布'),
            iframes: document.querySelectorAll('iframe').length,
            firebase_element: document.querySelector('fire-rules-editor, fire-rules, [data-test-id*="rules"]') ? true : false
        })
    """)
    print(f"\nEditors: {editors}")
    
    # Check full HTML of the main content area
    html = js(ws, "document.querySelector('firebase-app, body')?.innerHTML?.substring(0, 5000)")
    print(f"\nHTML:\n{html}")
    
    ws.close()

if __name__ == "__main__":
    main()

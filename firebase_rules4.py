"""
Firebase Rules - Chinese UI edition
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223

def evaluate(ws, expr, timeout=10):
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(0.5); raw = ws.recv()
        except websocket.WebSocketTimeoutException: continue
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError: continue
        if resp.get("id") == msg_id:
            exc = resp.get("result", {}).get("exceptionDetails")
            if exc: print(f"[JS] {exc.get('text','')}"); return None
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def main():
    print("=" * 60)
    print("Firebase - Chinese Rules Tab")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Click Rules tab by ID
    print("[1/5] Clicking 規則 tab (#mat-tab-link-1)...")
    evaluate(ws, """
        document.querySelector('#mat-tab-link-1')?.click();
    """)
    time.sleep(5)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL: {url}")
    
    # Check if we're on rules page
    body = evaluate(ws, "document.body.innerText?.substring(0, 1000)", timeout=10)
    print(f"   Body: {body[:500]}")
    
    # Look for editor
    has_editor = evaluate(ws, """
        document.querySelector('.monaco-editor, .CodeMirror, [role="textbox"], .ace-editor, textarea') !== null
    """)
    print(f"   Has editor: {has_editor}")
    
    # Get all textarea-like elements
    editors = evaluate(ws, """
        JSON.stringify({
            monaco: document.querySelectorAll('.monaco-editor').length,
            cm: document.querySelectorAll('.CodeMirror').length,
            textarea: document.querySelectorAll('textarea').length,
            textbox: document.querySelectorAll('[role="textbox"]').length,
            ace: document.querySelectorAll('.ace-editor').length,
        })
    """)
    print(f"   Editors: {editors}")
    
    # Look for anything that could be an editor
    code_elements = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('.view-lines, .ace_content, .cm-content, pre, code, .editor, .rules-editor'))
            .map(e => ({ tag: e.tagName, cls: e.className.substring(0, 60), text: (e.innerText || '').substring(0, 100) })))
    """)
    print(f"   Code elements: {code_elements}")
    
    # Maybe it's an iframe? 
    iframes = evaluate(ws, """
        document.querySelectorAll('iframe').length
    """)
    print(f"   Iframes: {iframes}")
    
    # Try to access iframe content
    iframe_src = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('iframe')).map(f => f.src || f.id || 'unknown'))
    """)
    print(f"   Iframe srcs: {iframe_src}")
    
    ws.close()
    print("\n✅ Checked!")

if __name__ == "__main__":
    main()

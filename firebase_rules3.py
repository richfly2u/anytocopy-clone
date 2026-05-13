"""
Firebase Rules - click through nav properly
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

def click_by_text(ws, text):
    return evaluate(ws, f"""
        (() => {{
            const items = document.querySelectorAll('a, button, span, [role="tab"], [role="button"], li');
            for (const el of items) {{
                if (el.innerText && el.innerText.trim() === {json.dumps(text)}) {{
                    el.click();
                    return 'clicked: ' + {json.dumps(text)};
                }}
            }}
            for (const el of items) {{
                if (el.innerText && el.innerText.trim().includes({json.dumps(text)})) {{
                    el.click();
                    return 'clicked(partial): ' + {json.dumps(text)};
                }}
            }}
            return 'not found: ' + {json.dumps(text)};
        }})()
    """)

def main():
    print("=" * 60)
    print("Firebase - Navigate to Firestore then Rules")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/overview")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Step 1: Click Firestore in sidebar
    print("[1/5] Clicking Firestore in sidebar...")
    r = click_by_text(ws, "Firestore")
    print(f"   {r}")
    time.sleep(5)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL: {url}")
    
    # Step 2: Click Rules tab
    print("[2/5] Looking for Rules tab...")
    
    # Get all tabs
    tabs = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('[role="tab"], .firebase-nav-item, .tab')).map(t => ({
            text: (t.innerText || '').trim(),
            role: t.getAttribute('role') || '',
            selected: t.getAttribute('aria-selected') || '',
            tag: t.tagName
        })))
    """, timeout=10)
    print(f"   Tabs: {tabs}")
    
    r = click_by_text(ws, "Rules")
    print(f"   {r}")
    time.sleep(5)
    
    url2 = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL after: {url2}")
    
    # Step 3: Get the rules editor content
    print("[3/5] Looking for rules editor...")
    
    # Check page content
    body = evaluate(ws, "document.body.innerText?.substring(0, 2000)", timeout=10)
    print(f"   Page: {body[:1000]}")
    
    # Check all interactive elements
    elements = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button, a, [role="tab"], [role="button"]')).map(el => ({
            text: (el.innerText || '').trim().substring(0, 40),
            aria: (el.getAttribute('aria-label') || '').substring(0, 30),
            id: (el.id || '').substring(0, 30)
        })).filter(e => e.text || e.aria))
    """, timeout=10)
    print(f"   Elements: {elements[:2000]}")
    
    # See if the rules editor is visible
    has_editor = evaluate(ws, """
        document.querySelector('.monaco-editor, .CodeMirror, [role="textbox"], .ace_editor, textarea, .firebase-rules-editor') !== null
    """)
    print(f"   Has editor: {has_editor}")
    
    if has_editor:
        # Set rules
        new_rules = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if true;
    }
  }
}"""
        
        evaluate(ws, f"""
            // Try all editor types
            const cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {{
                cm.CodeMirror.setValue({json.dumps(new_rules)});
                return;
            }}
            const ta = document.querySelector('textarea');
            if (ta) {{
                const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                ns.call(ta, {json.dumps(new_rules)});
                ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                return;
            }}
            const tb = document.querySelector('[role="textbox"]');
            if (tb) {{ tb.innerText = {json.dumps(new_rules)}; }}
        """)
        time.sleep(2)
        print("[4/5] Rules set! Looking for Publish...")
        
        r = click_by_text(ws, "Publish")
        print(f"   Publish: {r}")
        time.sleep(3)
        
        r2 = click_by_text(ws, "Confirm")
        print(f"   Confirm: {r2}")
        time.sleep(3)
    
    # Final status
    print("[5/5] Final check...")
    final_body = evaluate(ws, "document.body.innerText?.substring(0, 1000)", timeout=10)
    print(f"   Final: {final_body[:500]}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

"""
Update Firestore security rules in Firebase Console
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
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False

def click_by_text(ws, text, tag="button"):
    return evaluate(ws, f"""
        (() => {{
            const items = Array.from(document.querySelectorAll('{tag}'));
            let t = items.find(el => el.innerText.trim() === {json.dumps(text)});
            if (t) {{ t.click(); return 'clicked'; }}
            t = items.find(el => el.innerText.trim().includes({json.dumps(text)}));
            if (t) {{ t.click(); return 'clicked'; }}
            return 'not found';
        }})()
    """)

def main():
    print("=" * 60)
    print("Firebase Console - Firestore Rules")
    print("=" * 60)
    
    # Go to Firebase Console for bentodish-alan
    print("[1/5] Opening Firebase Console...")
    tab_id = create_tab("https://console.firebase.google.com/project/bentodish-alan/firestore/rules")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    wait_for_nav(ws)
    time.sleep(3)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL: {url}")
    
    # Check if we need to log in
    body = evaluate(ws, "document.body.innerText?.substring(0, 1000)", timeout=10)
    print(f"   Body: {body}")
    
    # If Google login page
    if "signin" in url.lower() or "accounts.google.com" in url:
        print("[!] Need Google login. Please log into Google in the browser tab...")
        print("    Then press Enter to continue...")
        input()
        wait_for_nav(ws)
        time.sleep(3)
    
    # Check current rules
    print("[2/5] Reading current rules...")
    body2 = evaluate(ws, "document.body.innerText?.substring(0, 3000)", timeout=10)
    print(f"   Current page: {body2[:1500]}")
    
    # Look for the rules editor
    rules_text = evaluate(ws, """
        // Try to get the rules text from the editor
        const editors = document.querySelectorAll('.CodeMirror, .monaco-editor, textarea, [role="textbox"]');
        for (const e of editors) {
            if (e.innerText || e.value || e.textContent) {
                return (e.innerText || e.value || e.textContent).substring(0, 2000);
            }
        }
        return 'no editor found';
    """, timeout=10)
    print(f"   Rules editor content:\n{rules_text}")
    
    # Find buttons related to publishing rules
    print("[3/5] Looking for Publish button...")
    btns = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button, span, a')).map(el => ({
            text: (el.innerText || '').trim().substring(0, 40),
            role: el.getAttribute('role') || '',
            tag: el.tagName
        })))
    """, timeout=10)
    print(f"   Buttons: {btns}")
    
    # Try to click into the editor if it's CodeMirror/Monaco
    print("[4/5] Clicking into the rules editor...")
    clicked = evaluate(ws, """
        (() => {
            const editors = document.querySelectorAll('.CodeMirror, .monaco-editor, [role="textbox"]');
            for (const e of editors) {
                e.click();
                return 'clicked editor';
            }
            return 'no editor to click';
        })()
    """)
    print(f"   {clicked}")
    time.sleep(1)
    
    # Try to set rules via the editor
    print("[5/5] Setting new Firestore rules...")
    
    new_rules = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Allow read/write to any document (for personal dashboard)
    match /{document=**} {
      allow read, write: if true;
    }
  }
}"""
    
    # Try to set the value via the editor API
    set_result = evaluate(ws, f"""
        (() => {{
            // Try monaco editor
            if (typeof monaco !== 'undefined' && monaco.editor) {{
                const editors = monaco.editor.getEditors();
                if (editors.length > 0) {{
                    editors[0].setValue({json.dumps(new_rules)});
                    return 'set via monaco';
                }}
            }}
            // Try CodeMirror
            const cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {{
                cm.CodeMirror.setValue({json.dumps(new_rules)});
                return 'set via codemirror';
            }}
            // Try textarea
            const ta = document.querySelector('textarea');
            if (ta) {{
                const nativeSet = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSet.call(ta, {json.dumps(new_rules)});
                ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                return 'set via textarea';
            }}
            // Try contenteditable
            const ce = document.querySelector('[contenteditable="true"], [role="textbox"]');
            if (ce) {{
                ce.innerText = '';
                ce.focus();
                document.execCommand('insertText', false, {json.dumps(new_rules)});
                return 'set via contenteditable';
            }}
            return 'no editor found';
        }})()
    """)
    print(f"   Set rules result: {set_result}")
    time.sleep(2)
    
    # Click Publish
    publish_result = click_by_text(ws, "Publish")
    print(f"   Publish: {publish_result}")
    time.sleep(3)
    
    # Confirm if needed
    confirm = click_by_text(ws, "Confirm")
    print(f"   Confirm: {confirm}")
    time.sleep(2)
    
    # Final check
    final_body = evaluate(ws, "document.body.innerText?.substring(0, 500)", timeout=10)
    print(f"\n   Final body: {final_body}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

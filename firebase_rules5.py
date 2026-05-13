"""
Add dashboard rule to Firestore security rules via CodeMirror
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
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def click_by_text(ws, text):
    return evaluate(ws, f"""
        (() => {{
            for (const el of document.querySelectorAll('button, a, span, [role="button"], [role="tab"]')) {{
                if (el.innerText && el.innerText.trim() === {json.dumps(text)})
                {{ el.click(); return 'clicked'; }}
            }}
            for (const el of document.querySelectorAll('button, a, span, [role="button"], [role="tab"]')) {{
                if (el.innerText && el.innerText.trim().includes({json.dumps(text)}))
                {{ el.click(); return 'clicked(partial)'; }}
            }}
            return 'not found';
        }})()
    """)

def main():
    print("=" * 60)
    print("Add Dashboard Rule to Firestore")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(3)
    
    # Click Rules tab
    print("[1/4] Clicking 規則 tab...")
    evaluate(ws, "document.querySelector('#mat-tab-link-1')?.click()")
    time.sleep(5)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL: {url}")
    
    # Get the existing rules via CodeMirror
    print("[2/4] Reading current rules...")
    current_rules = evaluate(ws, """
        (() => {
            const cm = document.querySelector('.CodeMirror');
            return cm && cm.CodeMirror ? cm.CodeMirror.getValue() : 'no codemirror';
        })()
    """)
    print(f"   Current rules:\n{current_rules}")
    
    # Add the dashboard rule before closing
    new_rule = """
    match /dashboard/{document=**} {
      allow read, write: if true;
    }"""
    
    # Insert before the final closing brace of the match /databases block
    new_rules = current_rules.rstrip()
    # Find the last closing } that closes the match /databases
    # Insert before last }
    if new_rules.endswith('}'):
        # Add before the last line
        lines = new_rules.split('\n')
        # Find where to insert
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped == '}':
                # Insert before this line
                lines.insert(i, new_rule)
                new_rules = '\n'.join(lines)
                break
        else:
            new_rules = new_rules + new_rule + '\n}'
    else:
        new_rules = new_rules + '\n' + new_rule
    
    print(f"\n   New rules:\n{new_rules}")
    
    # Set the new rules via CodeMirror API
    print("[3/4] Setting new rules...")
    set_result = evaluate(ws, f"""
        (() => {{
            const cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {{
                cm.CodeMirror.setValue({json.dumps(new_rules)});
                return 'set via codemirror';
            }}
            return 'no codemirror';
        }})()
    """)
    print(f"   Set result: {set_result}")
    time.sleep(2)
    
    # Click Publish button
    print("[4/4] Publishing...")
    
    # Find Publish button
    publish_btn = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
            text: (b.innerText || '').trim().substring(0, 20),
            disabled: b.disabled || false
        })).filter(b => b.text))
    """)
    print(f"   Buttons: {publish_btn}")
    
    r = click_by_text(ws, "發布")
    print(f"   發布: {r}")
    time.sleep(3)
    
    # Check for confirm dialog
    r2 = click_by_text(ws, "確認")
    print(f"   確認: {r2}")
    time.sleep(3)
    
    # Final check
    final_text = evaluate(ws, "document.body.innerText?.substring(0, 500)", timeout=10)
    print(f"\n   Final: {final_text[:300]}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

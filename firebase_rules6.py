"""
Fix dashboard rule position in Firestore
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
            for (const el of document.querySelectorAll('button, a, span, [role="button"]')) {{
                if (el.innerText && el.innerText.trim() === {json.dumps(text)})
                {{ el.click(); return 'clicked'; }}
            }}
            for (const el of document.querySelectorAll('button, a, span, [role="button"]')) {{
                if (el.innerText && el.innerText.trim().includes({json.dumps(text)}))
                {{ el.click(); return 'clicked(partial)'; }}
            }}
            return 'not found';
        }})()
    """)

def main():
    print("=" * 60)
    print("Fix Dashboard Rule Position")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(3)
    
    # Click Rules tab
    evaluate(ws, "document.querySelector('#mat-tab-link-1')?.click()")
    time.sleep(5)
    
    # Read current rules
    current = evaluate(ws, """
        (() => {
            const cm = document.querySelector('.CodeMirror');
            return cm && cm.CodeMirror ? cm.CodeMirror.getValue() : null;
        })()
    """)
    print(f"Current rules:\n{current}")
    
    # Fix the rules - put dashboard INSIDE match /databases
    lines = current.split('\n')
    
    # Find the last non-empty closing brace that closes match /databases
    # Count nesting:
    # line "  match /databases/{database}/documents {" -> nesting starts
    # The closing of this is the last `  }` before the misplaced dashboard rule
    
    new_lines = []
    inserted = False
    for line in lines:
        stripped = line.strip()
        # If we see the misplaced dashboard rule, skip it (we'll insert correctly)
        if stripped.startswith('match /dashboard/') and not inserted:
            continue
        if stripped == '}' and not inserted:
            # This is the closing of databases block
            # Insert dashboard rule before it
            new_lines.append('')
            new_lines.append('    match /dashboard/{document=**} {')
            new_lines.append('      allow read, write: if true;')
            new_lines.append('    }')
            new_lines.append('')
            inserted = True
        new_lines.append(line)
    
    new_rules = '\n'.join(new_lines)
    print(f"\nFixed rules:\n{new_rules}")
    
    # Set in CodeMirror
    evaluate(ws, f"""
        const cm = document.querySelector('.CodeMirror');
        if (cm && cm.CodeMirror) {{
            cm.CodeMirror.setValue({json.dumps(new_rules)});
        }}
    """)
    time.sleep(2)
    
    # Publish
    r = click_by_text(ws, "發布")
    print(f"\n發布: {r}")
    time.sleep(3)
    
    # Verify - read back
    final = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? cm.CodeMirror.getValue() : null;
    """)
    print(f"Final rules:\n{final}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

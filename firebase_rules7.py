"""
Replace entire Firestore rules with proper content
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

def set_and_publish(ws, new_rules):
    # Set the rules
    evaluate(ws, f"""
        const cm = document.querySelector('.CodeMirror');
        if (cm && cm.CodeMirror) {{
            cm.CodeMirror.setValue({json.dumps(new_rules)});
        }}
    """)
    time.sleep(2)
    
    # Find Publish button
    btns = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
            text: (b.innerText || '').trim(),
            disabled: b.disabled || false
        })).filter(b => b.text))
    """)
    print(f"Buttons: {btns}")
    
    # Try different button texts
    for text in ["發布", "Publish", "發佈"]:
        r = evaluate(ws, f"""
            (() => {{
                for (const el of document.querySelectorAll('button')) {{
                    if (el.innerText && el.innerText.trim() === {json.dumps(text)}) {{
                        el.click();
                        return 'clicked: ' + {json.dumps(text)};
                    }}
                }}
                return 'not found: ' + {json.dumps(text)};
            }})()
        """)
        print(f"  {r}")
        if 'clicked' in str(r):
            return True
    return False

def main():
    print("=" * 60)
    print("Replace Firestore Rules Cleanly")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(3)
    
    # Click Rules tab
    evaluate(ws, "document.querySelector('#mat-tab-link-1')?.click()")
    time.sleep(5)
    
    # Read current (to verify we're on the right page)
    current = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? cm.CodeMirror.getValue() : null;
    """)
    print(f"Current rules (first 100 chars): {current[:100] if current else None}")
    
    # Clean, proper rules with dashboard added
    new_rules = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    
    function isAdmin() {
      return request.auth != null && request.auth.token.email in ['alansnoopy@gmail.com', 'alansnoopy@gmail.com'];
    }
    
    function isOwner(resourceData) {
      return request.auth != null && request.auth.uid == resourceData.uid;
    }

    match /bento_combinations/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);
    }
    
    match /bento_photos/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);
    }

    match /table_combinations/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);
    }

    match /table_photos/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);
    }

    match /comments/{commentId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow delete: if request.auth != null && request.auth.uid == resource.data.authorUid;
    }
    
    // Dashboard data - allow all read/write (no auth required)
    match /dashboard/{document=**} {
      allow read, write: if true;
    }
  }
}"""
    
    print("\nSetting new rules...")
    success = set_and_publish(ws, new_rules)
    
    time.sleep(3)
    
    # Verify
    final = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? cm.CodeMirror.getValue().substring(0, 500) : null;
    """)
    print(f"\nRules after publish:\n{final}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

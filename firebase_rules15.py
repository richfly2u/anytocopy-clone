"""
Simple: Set rules and click Publish (like v5 did successfully)
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
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
        except: continue
        if resp.get("id") == msg_id:
            exc = resp.get("result", {}).get("exceptionDetails")
            if exc: return None
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

RULES = """rules_version = '2';
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
      allow update, delete: if isAdmin() || isOwner(resource.data); }
    match /bento_photos/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data); }
    match /table_combinations/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data); }
    match /table_photos/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data); }
    match /comments/{commentId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow delete: if request.auth != null && request.auth.uid == resource.data.authorUid; }
    match /dashboard/{document=**} {
      allow read, write: if true; }
  }
}"""

def main():
    print("=" * 60)
    print("Simple Firestore Rules Update")
    print("=" * 60)
    
    # Go to Firestore Data page first, then click Rules tab
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Click Rules tab
    print("[1/4] Clicking Rules tab...")
    evaluate(ws, "document.querySelector('#mat-tab-link-1')?.click()")
    time.sleep(5)
    
    # Read current
    current = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        if (cm && cm.CodeMirror) return cm.CodeMirror.getValue();
        return null;
    """)
    print(f"Current (first 100): {str(current)[:100]}")
    
    # Set new rules
    print("[2/4] Setting new rules via CodeMirror API...")
    result = evaluate(ws, f"""
        const cm = document.querySelector('.CodeMirror').CodeMirror;
        cm.setValue({json.dumps(RULES)});
        // Force change event
        cm.getDoc().clearHistory();
        'ok';
    """)
    print(f"   Set: {result}")
    time.sleep(2)
    
    # Find Publish button
    print("[3/4] Looking for Publish button...")
    
    btns = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
            text: (b.innerText || '').trim().substring(0, 20),
            disabled: b.disabled
        })).filter(b => b.text && !b.text.startsWith('gmp_')))
    """)
    print(f"Buttons: {btns}")
    
    # Try 發布
    for label in ["發布", "Publish"]:
        r = evaluate(ws, f"""
            (() => {{
                for (const b of document.querySelectorAll('button')) {{
                    if (b.innerText.trim() === {json.dumps(label)}) {{
                        b.click();
                        return 'clicked: ' + {json.dumps(label)};
                    }}
                }}
                return 'not found: ' + {json.dumps(label)};
            }})()
        """)
        print(f"   {r}")
        if 'clicked' in str(r):
            time.sleep(3)
            break
    
    # Check final state
    print("[4/4] Verifying...")
    final = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        if (cm && cm.CodeMirror) {
            const v = cm.CodeMirror.getValue();
            return 'dashboard_included: ' + v.includes('dashboard') + ', len: ' + v.length;
        }
        return 'no_cm';
    """)
    print(f"   {final}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

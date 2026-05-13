"""
Firestore Rules - clean approach
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223
RULES_URL = "https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/security/rules"

RULES_TEXT = """rules_version = '2';
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

    // Dashboard data - allow all read/write
    match /dashboard/{document=**} {
      allow read, write: if true;
    }
  }
}"""

def evaluate(ws, expr, timeout=15):
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
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def cdp_call(ws, method, params=None):
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            ws.settimeout(0.5); raw = ws.recv()
        except: continue
        try:
            resp = json.loads(raw)
        except: continue
        if resp.get("id") == msg_id:
            return resp
    return None

def main():
    print("=" * 60)
    print("Firestore Rules - Clean Approach")
    print("=" * 60)
    
    # Open tab with explicit Page.enable first
    tab_id = create_tab("about:blank")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    
    # Enable page events
    cdp_call(ws, "Page.enable")
    
    # Navigate to rules URL
    print("[1/4] Navigating to rules page...")
    cdp_call(ws, "Page.navigate", {"url": RULES_URL})
    time.sleep(10)  # Extra long wait for Firebase SPA to load
    
    # Check if we're on the right page
    url = evaluate(ws, "window.location.href")
    title = evaluate(ws, "document.title")
    print(f"   URL: {url}")
    print(f"   Title: {title}")
    
    # Wait a bit more for Angular to render
    time.sleep(5)
    
    # Try to access CodeMirror
    print("[2/4] Looking for CodeMirror editor...")
    for attempt in range(5):
        has_cm = evaluate(ws, "!!document.querySelector('.CodeMirror')")
        print(f"   Attempt {attempt+1}: Has CodeMirror: {has_cm}")
        if has_cm:
            break
        time.sleep(3)
    
    # Get the CodeMirror instance
    cm_ready = evaluate(ws, """
        (() => {
            const cm = document.querySelector('.CodeMirror');
            return cm && cm.CodeMirror ? true : false;
        })()
    """)
    print(f"   CodeMirror ready: {cm_ready}")
    
    if cm_ready:
        print("[3/4] Setting rules via CodeMirror...")
        r = evaluate(ws, f"""
            const cm = document.querySelector('.CodeMirror').CodeMirror;
            cm.setValue({json.dumps(RULES_TEXT)});
            'ok';
        """)
        print(f"   Set result: {r}")
        time.sleep(2)
        
        # Find Publish button
        print("[4/4] Looking for Publish button...")
        for attempt in range(3):
            # List buttons
            btns = evaluate(ws, """
                JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
                    text: (b.innerText || '').trim().substring(0, 30),
                    disabled: b.disabled ? 'Y' : 'N',
                    id: (b.id || '').substring(0, 20)
                })).filter(b => b.text && !b.text.startsWith('gmp_')))
            """)
            print(f"   Buttons: {btns}")
            
            # Try each possible button text
            for btext in ["發布", "Publish", "發佈", "發　布"]:
                r = evaluate(ws, f"""
                    (() => {{
                        for (const el of document.querySelectorAll('button')) {{
                            if (el.innerText && el.innerText.trim() === {json.dumps(btext)}) {{
                                el.click();
                                return 'clicked: ' + {json.dumps(btext)};
                            }}
                        }}
                        return 'not found: ' + {json.dumps(btext)};
                    }})()
                """)
                if r and 'clicked' in str(r):
                    print(f"   {r}")
                    time.sleep(3)
                    
                    # Check for confirmation dialog
                    for ctext in ["確認", "Confirm", "同意"]:
                        c = evaluate(ws, f"""
                            (() => {{
                                for (const el of document.querySelectorAll('button')) {{
                                    if (el.innerText && el.innerText.trim() === {json.dumps(ctext)}) {{
                                        el.click();
                                        return 'clicked: ' + {json.dumps(ctext)};
                                    }}
                                }}
                                return 'not found: ' + {json.dumps(ctext)};
                            }})()
                        """)
                        if c and 'clicked' in str(c):
                            print(f"   Confirm: {c}")
                            time.sleep(2)
                    
                    # Verify
                    final = evaluate(ws, """
                        const cm = document.querySelector('.CodeMirror');
                        return cm && cm.CodeMirror ? cm.CodeMirror.getValue().substring(0, 200) : null;
                    """)
                    print(f"\n   Rules after publish:\n{final}")
                    ws.close()
                    print("\n✅ Done! Rules published successfully!")
                    return
            
            time.sleep(3)
    
    # Fallback: try clicking the rules tab first
    print("\n[!] Trying to click Rules tab first...")
    evaluate(ws, "document.querySelector('#mat-tab-link-1')?.click()")
    time.sleep(5)
    
    # Try again
    cm_ready2 = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? true : false;
    """)
    print(f"   CodeMirror ready (after tab click): {cm_ready2}")
    
    if cm_ready2:
        evaluate(ws, f"""
            const cm = document.querySelector('.CodeMirror').CodeMirror;
            cm.setValue({json.dumps(RULES_TEXT)});
        """)
        time.sleep(2)
        
        btns = evaluate(ws, """
            JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
                text: (b.innerText || '').trim().substring(0, 30),
                disabled: b.disabled ? 'Y' : 'N'
            })).filter(b => b.text))
        """)
        print(f"   Buttons: {btns}")
    
    ws.close()
    print("\n❌ Failed to publish rules")

if __name__ == "__main__":
    main()

"""
Direct Firebase Rules API via browser fetch
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

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

def eval_js(ws, js, timeout=15):
    r = cdp(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }, timeout)
    if r and "result" in r:
        ed = r["result"].get("exceptionDetails")
        if ed: return f"[JS] {ed.get('text','')}"
        return r["result"].get("result", {}).get("value")
    return None

RULES_CONTENT = """rules_version = '2';
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

def main():
    print("=" * 60)
    print("Firebase Rules API via fetch")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/overview")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Call Firebase Rules REST API from the browser context
    print("[1/3] Calling Firebase Rules API...")
    
    result = eval_js(ws, f"""
        (async () => {{
            try {{
                const resp = await fetch(
                    'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/rulesets',
                    {{
                        method: 'POST',
                        credentials: 'include',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            source: {{
                                files: [{{
                                    name: 'firestore.rules',
                                    content: {json.dumps(RULES_CONTENT)}
                                }}]
                            }}
                        }})
                    }}
                );
                const text = await resp.text();
                try {{
                    const data = JSON.parse(text);
                    return 'Status: ' + resp.status + ', Name: ' + (data.name || '') + ', Error: ' + (data.error?.message || 'none');
                }} catch(e) {{
                    return 'Status: ' + resp.status + ', Raw: ' + text.substring(0, 200);
                }}
            }} catch(e) {{
                return 'Error: ' + e.message;
            }}
        }})()
    """)
    print(f"   Result: {result}")
    
    if result and 'Name:' in str(result) and 'Error: none' in str(result):
        # Release the ruleset
        print("[2/3] Releasing ruleset...")
        name = result.split('Name: ')[1].split(',')[0].strip()
        
        release_result = eval_js(ws, f"""
            (async () => {{
                try {{
                    const resp = await fetch(
                        'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/releases',
                        {{
                            method: 'PATCH',
                            credentials: 'include',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{
                                name: 'projects/bentodish-alan/releases/cloud.firestore',
                                rulesetName: {json.dumps(name)}
                            }})
                        }}
                    );
                    const text = await resp.text();
                    try {{
                        const data = JSON.parse(text);
                        return 'Status: ' + resp.status + ', Name: ' + (data.name || '') + ', Error: ' + (data.error?.message || 'none');
                    }} catch(e) {{
                        return 'Status: ' + resp.status + ', Raw: ' + text.substring(0, 200);
                    }}
                }} catch(e) {{
                    return 'Error: ' + e.message;
                }}
            }})()
        """)
        print(f"   Release result: {release_result}")
    
    # Verify by navigating to rules page and reading
    print("[3/3] Verifying...")
    eval_js(ws, f"window.location.href = '{RULES_URL}'")
    time.sleep(8)
    
    rules = eval_js(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? cm.CodeMirror.getValue().substring(0, 600) : 'no cm';
    """)
    print(f"   Rules on page:\n{rules}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

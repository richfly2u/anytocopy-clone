"""
Get OAuth token from Google Cloud Console
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, time

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
        if ed: return f"[ERR] {ed.get('text','')}"
        return r["result"].get("result", {}).get("value")
    return None

CONTENT = """rules_version = '2';
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
    // Dashboard - allow all
    match /dashboard/{document=**} {
      allow read, write: if true;
    }
  }
}"""

def main():
    print("=" * 60)
    print("Get GCP OAuth token from Cloud Console")
    print("=" * 60)
    
    # Go to Cloud Console Firestore page (which has gapi loaded)
    tab_id = create_tab("https://console.cloud.google.com/firestore/databases/-default-/rules?project=bentodish-alan")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(8)
    
    url = eval_js(ws, "window.location.href")
    title = eval_js(ws, "document.title")
    print(f"URL: {url}")
    print(f"Title: {title}")
    
    # Check gapi
    has_gapi = eval_js(ws, "typeof gapi !== 'undefined'")
    print(f"Has gapi: {has_gapi}")
    
    if has_gapi:
        # Give it a moment to initialize
        time.sleep(3)
        
        token = eval_js(ws, """
            (async () => {
                try {
                    // Try to get the auth token
                    if (gapi.auth) {
                        const t = gapi.auth.getToken();
                        if (t && t.access_token) return t.access_token;
                    }
                    // Try gapi.auth2
                    if (gapi.auth2) {
                        const auth = gapi.auth2.getAuthInstance();
                        if (auth) {
                            const user = auth.currentUser.get();
                            if (user) {
                                const response = user.getAuthResponse();
                                if (response.access_token) return response.access_token;
                            }
                        }
                    }
                    // Try gapi.client.getToken
                    if (gapi.client && gapi.client.getToken) {
                        const t = gapi.client.getToken();
                        if (t && t.access_token) return t.access_token;
                    }
                    return null;
                } catch(e) {
                    return 'error: ' + e.message;
                }
            })()
        """)
        
        if token and token.startswith('error'):
            print(f"Token error: {token}")
        elif token and len(token) > 20:
            print(f"Token obtained! {token[:30]}...")
            
            # Use the token for Firebase Rules API
            print("\nCreating ruleset...")
            result = eval_js(ws, f"""
                (async () => {{
                    const resp = await fetch(
                        'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/rulesets',
                        {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                'Authorization': 'Bearer {token}'
                            }},
                            body: JSON.stringify({{
                                source: {{
                                    files: [{{
                                        name: 'firestore.rules',
                                        content: {json.dumps(CONTENT)}
                                    }}]
                                }}
                            }})
                        }}
                    );
                    const data = await resp.json();
                    return JSON.stringify({{status: resp.status, name: data.name, error: data.error?.message}});
                }})()
            """)
            print(f"Result: {result}")
            
            if result and '"name":' in str(result) and '"error":null' in str(result):
                try:
                    data = json.loads(result)
                    name = data.get('name', '')
                    if name:
                        print(f"\nReleasing ruleset: {name}")
                        release = eval_js(ws, f"""
                            (async () => {{
                                const resp = await fetch(
                                    'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/releases',
                                    {{
                                        method: 'PATCH',
                                        headers: {{
                                            'Content-Type': 'application/json',
                                            'Authorization': 'Bearer {token}'
                                        }},
                                        body: JSON.stringify({{
                                            name: 'projects/bentodish-alan/releases/cloud.firestore',
                                            rulesetName: {json.dumps(name)}
                                        }})
                                    }}
                                );
                                const data = await resp.json();
                                return JSON.stringify({{status: resp.status, name: data.name, error: data.error?.message}});
                            }})()
                        """)
                        print(f"Release: {release}")
                except json.JSONDecodeError:
                    pass
            else:
                print("Failed to create ruleset")
        else:
            print(f"No token available: {token}")
    else:
        print("gapi not available on this page")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

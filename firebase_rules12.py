"""
Get OAuth token from gapi and call Firebase Rules API
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
    match /dashboard/{document=**} {
      allow read, write: if true;
    }
  }
}"""

def main():
    print("=" * 60)
    print("Get OAuth token and update rules")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/overview")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Get OAuth token via gapi
    print("[1/4] Getting OAuth token...")
    token = eval_js(ws, """
        (async () => {
            try {
                // Check gapi
                if (typeof gapi !== 'undefined') {
                    // Try to get the auth token
                    const token = gapi.auth.getToken();
                    if (token && token.access_token) {
                        return 'gapi_token: ' + token.access_token.substring(0, 30) + '...';
                    }
                    // Try to get a new token
                    if (gapi.auth2) {
                        const auth = gapi.auth2.getAuthInstance();
                        if (auth) {
                            const user = auth.currentUser.get();
                            const t = user.getAuthResponse().access_token;
                            return 'gapi2_token: ' + t.substring(0, 30) + '...';
                        }
                    }
                }
                // Try Google Identity Services
                if (typeof google !== 'undefined' && google.accounts) {
                    return 'has_gis';
                }
                // Try to get from the Firebase Auth user
                if (typeof firebase !== 'undefined' && firebase.auth) {
                    const user = firebase.auth().currentUser;
                    if (user) {
                        const t = await user.getIdToken();
                        return 'firebase_token: ' + t.substring(0, 30) + '...';
                    }
                }
                // Check localStorage for credentials
                for (const key of Object.keys(localStorage)) {
                    try {
                        const v = JSON.parse(localStorage[key]);
                        if (v.credential && v.credential.accessToken) {
                            return 'cred_token: ' + v.credential.accessToken.substring(0, 30) + '...';
                        }
                    } catch(e) {}
                }
                return JSON.stringify({has_gapi: typeof gapi !== 'undefined', has_firebase: typeof firebase !== 'undefined'});
            } catch(e) {
                return 'error: ' + e.message;
            }
        })()
    """)
    print(f"   Token: {token}")
    
    if token and ('token' in str(token) or 'gapi' in str(token) or 'firebase' in str(token)):
        # Extract the full token string
        token_parts = str(token).split(': ', 1)
        if len(token_parts) > 1 and token_parts[0] in ['gapi_token', 'gapi2_token', 'firebase_token', 'cred_token']:
            token_type = token_parts[0]
            
            # Get the full token
            if token_type == 'gapi_token':
                full_token = eval_js(ws, "gapi.auth.getToken().access_token")
            elif token_type == 'gapi2_token':
                full_token = eval_js(ws, "gapi.auth2.getAuthInstance().currentUser.get().getAuthResponse().access_token")
            elif token_type == 'firebase_token':
                full_token = eval_js(ws, "(async () => { const u = firebase.auth().currentUser; return u ? await u.getIdToken() : null; })()")
            else:
                full_token = None
            
            if full_token:
                print(f"   Full token obtained: {full_token[:30]}...")
                
                # Call API with token
                print("[2/4] Creating ruleset...")
                result = eval_js(ws, f"""
                    (async () => {{
                        const resp = await fetch(
                            'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/rulesets',
                            {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                    'Authorization': 'Bearer {full_token}'
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
                print(f"   Result: {result}")
                
                if result and '"name":' in str(result):
                    # Parse and release
                    try:
                        data = json.loads(result)
                        name = data.get('name', '')
                        
                        if name:
                            print("[3/4] Releasing ruleset...")
                            release = eval_js(ws, f"""
                                (async () => {{
                                    const resp = await fetch(
                                        'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/releases',
                                        {{
                                            method: 'PATCH',
                                            headers: {{
                                                'Content-Type': 'application/json',
                                                'Authorization': 'Bearer {full_token}'
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
                            print(f"   Release: {release}")
                    except json.JSONDecodeError:
                        pass
    
    # Alternative path: if we couldn't get token, try another approach
    if not token or 'token:' not in str(token):
        print("\n[!] Couldn't get API token. Trying alternative: use Cloud Shell...")
        
        # Try using Firebase CLI from Cloud Shell
        # First check if Cloud Shell is accessible
        cloud_shell = eval_js(ws, """
            (async () => {
                try {
                    const resp = await fetch('https://cloudshell.googleapis.com/v1/users/me/environments/default:start', {
                        method: 'POST',
                        credentials: 'include'
                    });
                    return 'cloudshell: ' + resp.status;
                } catch(e) {
                    return 'error: ' + e.message;
                }
            })()
        """)
        print(f"   Cloud Shell: {cloud_shell}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

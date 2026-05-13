"""
Get token via gapi.auth2 or gapi.auth.authorize
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
      return request.auth != null && request.auth.token.email in ['alansnoopy@gmail.com', 'alansnoopy@gmail.com'];}
    function isOwner(resourceData) {
      return request.auth != null && request.auth.uid == resourceData.uid;}
    match /bento_combinations/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);}
    match /bento_photos/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);}
    match /table_combinations/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);}
    match /table_photos/{docId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow update, delete: if isAdmin() || isOwner(resource.data);}
    match /comments/{commentId} {
      allow read: if true;
      allow create: if request.auth != null;
      allow delete: if request.auth != null && request.auth.uid == resource.data.authorUid;}
    match /dashboard/{document=**} { allow read, write: if true; }
  }
}"""

def main():
    print("=" * 60)
    print("Get GCP token via gapi")
    print("=" * 60)
    
    tab_id = create_tab("https://console.cloud.google.com/firestore/databases/-default-/security/rules?project=bentodish-alan")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(8)
    
    print(f"URL: {eval_js(ws, 'window.location.href')}")
    
    # List all gapi properties
    gapi_info = eval_js(ws, """
        JSON.stringify(Object.keys(gapi).filter(k => typeof gapi[k] !== 'function').slice(0, 20))
    """)
    print(f"gapi keys: {gapi_info}")
    
    # Try to get auth2 instance
    auth2_info = eval_js(ws, """
        (async () => {
            try {
                // Check if auth2 is already available
                if (gapi.auth2) {
                    const auth = gapi.auth2.getAuthInstance();
                    if (auth) {
                        const isSigned = auth.isSignedIn.get();
                        if (isSigned) {
                            const user = auth.currentUser.get();
                            const response = user.getAuthResponse();
                            if (response && response.access_token) {
                                return response.access_token;
                            }
                        }
                        return 'auth2_exists_but_not_signed_in:' + isSigned;
                    }
                    return 'auth2_no_instance';
                }
                // Try gapi.auth.authorize
                if (gapi.auth && gapi.auth.authorize) {
                    return 'has_authorize';
                }
                return 'no_auth2';
            } catch(e) {
                return 'error: ' + e.message;
            }
        })()
    """)
    print(f"auth2 info: {auth2_info}")
    
    # Check if Google Identity Services (GIS) is loaded
    gis_info = eval_js(ws, """
        JSON.stringify({
            has_google_oauth2: typeof google?.accounts?.oauth2 !== 'undefined',
            has_google_id: typeof google?.accounts?.id !== 'undefined',
        })
    """)
    print(f"GIS: {gis_info}")
    
    # Try to use gapi.auth.authorize to get a token
    if auth2_info == 'has_authorize':
        print("\nTrying gapi.auth.authorize...")
        result = eval_js(ws, """
            (async () => {
                return new Promise((resolve, reject) => {
                    gapi.auth.authorize({
                        client_id: gapi.auth.getClientId ? gapi.auth.getClientId() : null,
                        scope: 'https://www.googleapis.com/auth/cloud-platform',
                        immediate: true
                    }, (authResult) => {
                        if (authResult && authResult.access_token) {
                            resolve(authResult.access_token);
                        } else {
                            resolve('no_token: ' + JSON.stringify(authResult));
                        }
                    });
                });
            })()
        """)
        print(f"Authorize result: {result}")
        
        if result and len(str(result)) > 20 and 'no_token' not in str(result):
            token = result
            print(f"Got token: {token[:30]}...")
            
            # API call...
            api_result = eval_js(ws, f"""
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
                                source: {{ files: [{{ name: 'firestore.rules', content: {json.dumps(CONTENT)} }}] }}
                            }})
                        }}
                    );
                    const data = await resp.json();
                    return JSON.stringify({{status: resp.status, name: data.name, error: data.error?.message}});
                }})()
            """)
            print(f"API: {api_result}")
    
    # Try using fetch to Cloud APIs with cookies instead
    print("\nTrying with gapi.client request...")
    client_result = eval_js(ws, f"""
        (async () => {{
            try {{
                if (gapi.client) {{
                    // Try using gapi.client.request
                    const resp = await gapi.client.request({{
                        path: 'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/rulesets',
                        method: 'POST',
                        body: {json.dumps({{source: {{files: [{{name: 'firestore.rules', content: CONTENT}}]}}}})}
                    }});
                    return JSON.stringify({{status: 'done', name: resp.result?.name, error: resp.result?.error?.message}});
                }}
                return 'no gapi.client';
            }} catch(e) {{
                return 'error: ' + e.message;
            }}
        }})()
    """)
    print(f"gapi.client: {client_result}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

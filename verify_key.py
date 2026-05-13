"""
Verify Firebase API key
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

def js(ws, expr, timeout=15):
    r = cdp(ws, "Runtime.evaluate", {
        "expression": expr, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }, timeout)
    if r and "result" in r:
        ed = r["result"].get("exceptionDetails")
        if ed: return f"[ERR] {ed.get('text','')}"
        return r["result"].get("result", {}).get("value")
    return None

def main():
    # Create a fresh tab and use fetch to verify the API key
    tab_id = create_tab("about:blank")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    
    # Try different API key candidates
    keys_to_try = [
        "AIzaSyCRazQsleeT4H4Nt6VrqI1KGlfVenc",
    ]
    
    for key in keys_to_try:
        result = js(ws, f"""
            (async () => {{
                try {{
                    const resp = await fetch(
                        'https://firestore.googleapis.com/v1/projects/bentodish-alan/databases/(default)/documents?key={key}',
                        {{method: 'GET'}}
                    );
                    const text = await resp.text();
                    try {{
                        const data = JSON.parse(text);
                        if (data.documents) {{
                            return 'VALID_KEY: found ' + data.documents.length + ' documents';
                        }} else if (data.error) {{
                            return 'VALID_KEY but error: ' + data.error.message;
                        }} else {{
                            return 'VALID_KEY: ' + JSON.stringify(data).substring(0, 200);
                        }}
                    }} catch(e) {{
                        return 'RESPONSE: ' + resp.status + ' ' + text.substring(0, 200);
                    }}
                }} catch(e) {{
                    return 'FETCH_ERROR: ' + e.message;
                }}
            }})()
        """)
        print(f"Testing key '{key[:20]}...': {result}")
    
    ws.close()

if __name__ == "__main__":
    main()

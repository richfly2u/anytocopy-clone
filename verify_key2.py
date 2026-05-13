"""
Verify API key from Firebase Console page (same origin)
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
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/data")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Test API key from a Google-domain page
    key = "AIzaSyCRazQsleeT4H4Nt6VrqI1KGlfVenc"
    
    result = js(ws, f"""
        (async () => {{
            try {{
                const resp = await fetch(
                    'https://firestore.googleapis.com/v1/projects/bentodish-alan/databases/(default)/documents/dashboard/alantest?key={key}'
                );
                const text = await resp.text();
                try {{
                    const data = JSON.parse(text);
                    if (data.error) {{
                        if (data.error.status === 'NOT_FOUND') return 'VALID KEY - document not found (expected)';
                        return 'RESULT: ' + data.error.message;
                    }}
                    return 'FOUND: ' + JSON.stringify(data).substring(0, 300);
                }} catch(e) {{
                    return 'RAW: ' + resp.status + ' ' + text.substring(0, 200);
                }}
            }} catch(e) {{
                return 'ERR: ' + e.message;
            }}
        }})()
    """)
    print(f"Key test: {result}")
    
    ws.close()

if __name__ == "__main__":
    main()

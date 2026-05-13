"""
Get apiKey from GCP API credentials page
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
        if ed: return None
        return r["result"].get("result", {}).get("value")
    return None

def main():
    # Go to GCP credentials page
    tab_id = create_tab("https://console.cloud.google.com/apis/credentials?project=bentodish-alan")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(10)
    
    url = js(ws, "window.location.href")
    print(f"URL: {url}")
    
    # Get all API keys from the page
    text = js(ws, "document.body.innerText?.substring(0, 5000)")
    print(f"Page text: {text}")
    
    # Look for AIzaSy keys
    keys = js(ws, """
        const allText = document.body.innerText;
        const matches = allText.match(/AIzaSy[A-Za-z0-9_-]{30,}/g) || [];
        return JSON.stringify(matches);
    """)
    print(f"\nKeys found: {keys}")
    
    ws.close()

if __name__ == "__main__":
    main()

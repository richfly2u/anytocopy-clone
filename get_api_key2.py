"""
Extract Firebase API key from page source
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
    tab_id = create_tab("about:blank")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    
    # Navigate to the page source
    cdp(ws, "Page.enable")
    cdp(ws, "Page.navigate", {"url": "view-source:https://console.firebase.google.com/u/0/project/bentodish-alan/settings/general"})
    time.sleep(5)
    
    # Get the page source
    text = js(ws, "document.querySelector('pre')?.innerText || document.body.innerText")
    if text and len(text) > 100:
        # Search for apiKey
        for line in text.split('\n'):
            if 'apiKey' in line or 'AIzaSy' in line:
                print(f"Found: {line.strip()[:200]}")
    
    if not text:
        # view-source might not work, try getting the page source via CDP
        print("view-source didn't work, trying CDP...")
    
    ws.close()

if __name__ == "__main__":
    main()

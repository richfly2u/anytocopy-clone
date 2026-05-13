"""
Firestore Rules - take screenshot
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time, base64

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
        except json.JSONDecodeError: continue
        if resp.get("id") == msg_id:
            exc = resp.get("result", {}).get("exceptionDetails")
            if exc: return f"[ERROR] {exc.get('text','')}"
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def send_cdp(ws, method, params=None):
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

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def main():
    print("=" * 60)
    print("Screenshot Firestore Rules Page")
    print("=" * 60)
    
    # Navigate directly to the rules page
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/security/rules")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(8)
    
    # Check URL
    url = evaluate(ws, "window.location.href")
    print(f"URL: {url}")
    
    # Take screenshot
    result = send_cdp(ws, "Page.captureScreenshot", {"format": "png"})
    if result and "result" in result:
        img_data = result["result"]["data"]
        path = r"C:\Users\alan\Desktop\firestore_rules.png"
        with open(path, "wb") as f:
            f.write(base64.b64decode(img_data))
        print(f"Screenshot saved to {path}")
    else:
        print(f"Screenshot failed: {result}")
    
    # Get page text
    text = evaluate(ws, "document.body.innerText?.substring(0, 3000)")
    print(f"\nPage text:\n{text}")
    
    ws.close()

if __name__ == "__main__":
    main()

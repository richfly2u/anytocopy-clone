"""
Check if user has Render account and deploy backend
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223

def evaluate(ws, expr, timeout=10):
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": True
    }}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(1.0); raw = ws.recv()
        except websocket.WebSocketTimeoutException: continue
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError: continue
        if resp.get("id") == msg_id:
            exc = resp.get("result", {}).get("exceptionDetails")
            if exc: return {"error": exc.get("text", str(exc))}
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def main():
    print("=== Checking if Render is accessible ===")
    tab_id = create_tab("https://dashboard.render.com/")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    title = evaluate(ws, "document.title", timeout=10)
    print(f"URL: {url}")
    print(f"Title: {title}")
    
    text = evaluate(ws, "document.body.innerText?.substring(0, 2000)", timeout=10)
    print(f"Body: {text}")
    
    # Check for render.com dashboard or login
    if "login" in url.lower() or "sign" in url.lower() or "log in" in (text or "").lower():
        print("\nNot logged into Render. Need alternative backend deployment.")
        print("Options: Fly.io, Railway, or use the existing local server.")
        
        # Check if there's a GitHub login option on Render
        has_github = evaluate(ws, """
            document.body.innerText.includes('GitHub') || false
        """)
        print(f"GitHub login option: {has_github}")
    else:
        print("\nAlready on Render dashboard! Can deploy from GitHub repo.")
    
    ws.close()

if __name__ == "__main__":
    main()

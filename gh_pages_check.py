"""
Check GitHub Pages status via CDP
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
    tab_id = create_tab("https://github.com/richfly2u/daily-dashboard/settings/pages")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Read entire page content
    text = evaluate(ws, "document.body.innerText", timeout=15)
    print(text[:3000])
    
    # Check for the Pages URL and status
    print("\n--- Looking for key info ---")
    
    urls = evaluate(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('a'))
            .filter(a => a.href)
            .map(a => a.href)
            .filter(h => h.includes('github.io')))
    """, timeout=10)
    print(f"GitHub.io links: {urls}")
    
    # Check the branch source
    branch = evaluate(ws, """
        document.querySelector('[data-menu-button]')?.innerText?.trim() ||
        document.querySelector('summary')?.innerText?.trim() || 
        'not found'
    """, timeout=10)
    print(f"Branch selector text: {branch}")
    
    # Full HTML around the Pages section
    html = evaluate(ws, """
        document.querySelector('main')?.innerHTML?.substring(0, 5000) || 'no main'
    """, timeout=10)
    print(f"\n--- HTML snippet ---\n{html}")
    
    ws.close()

if __name__ == "__main__":
    main()

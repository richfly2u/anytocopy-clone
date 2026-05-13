"""
Resolve xhslink short URL via CDP (CentBrowser)
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time, re

CDP_PORT = 9223

def get_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=10).read())

def cdp_send(ws, method, params=None):
    mid = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    return mid

def eval_js(ws, expr, timeout=10):
    mid = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(0.3); raw = ws.recv()
        except: continue
        try:
            resp = json.loads(raw)
        except: continue
        if resp.get("id") == mid:
            ed = resp.get("result", {}).get("exceptionDetails")
            if ed: return f"[ERR] {ed.get('text','')}"
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def main():
    short_url = "http://xhslink.com/o/942pLthwTgS"
    
    # Create a new tab with the short URL
    print("[1/4] Creating new tab for short URL...")
    try:
        tab = get_json(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(short_url)}")
    except:
        # Try without quoting
        tab = get_json(f"http://127.0.0.1:{CDP_PORT}/json/new")
    
    page_id = tab["id"]
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}", timeout=30)
    time.sleep(2)
    
    # Navigate to short URL
    print("[2/4] Navigating to xhslink...")
    cdp_send(ws, "Page.navigate", {"url": short_url})
    time.sleep(8)
    
    current_url = eval_js(ws, "window.location.href")
    print(f"   Current URL after nav: {current_url}")
    
    # xhslink.com might redirect - give it time
    time.sleep(5)
    
    current_url2 = eval_js(ws, "window.location.href")
    print(f"   URL after waiting: {current_url2}")
    
    # Get page content
    title = eval_js(ws, "document.title")
    print(f"   Title: {title}")
    
    text = eval_js(ws, "document.body?.innerText?.substring(0, 3000) || ''")
    print(f"   Page text: {text[:1000]}")
    
    # Extract XHS note ID from URL
    if current_url2:
        m = re.search(r'/explore/([a-f0-9]{24,32})', current_url2)
        if m:
            note_id = m.group(1)
            print(f"\n   ✅ XHS Note ID: {note_id}")
            print(f"   Full URL: https://www.xiaohongshu.com/explore/{note_id}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

"""
Extract XHS note content via CDP - use existing tab or navigate
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

def cdp_recv_match(ws, target_id=None, method_filter=None, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            ws.settimeout(0.3); raw = ws.recv()
        except: continue
        try:
            msg = json.loads(raw)
        except: continue
        mid = msg.get("id")
        meth = msg.get("method", "")
        if target_id and mid == target_id:
            return msg
        if method_filter and meth in method_filter:
            return msg
    return None

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
    full_url = "https://www.xiaohongshu.com/explore/67fa6e61000000001f011125"  # resolved
    
    # Step 1: Resolve short URL
    print("[1/7] Resolving short URL...")
    try:
        req = urllib.request.Request(short_url, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=10)
        full_url = resp.url
        print(f"   Resolved: {full_url}")
    except:
        print(f"   Using fallback URL")
    
    note_id = None
    m = re.search(r'/explore/([a-f0-9]{24,32})', full_url)
    if m: note_id = m.group(1)
    print(f"   Note ID: {note_id}")
    
    # Step 2: Find existing XHS tab
    print("[2/7] Finding existing XHS tab...")
    xhs_tab = None
    try:
        tabs = get_json(f"http://127.0.0.1:{CDP_PORT}/json")
        for t in tabs:
            url = t.get("url", "")
            if "xiaohongshu.com" in url and note_id and note_id in url:
                xhs_tab = t
                print(f"   Found existing XHS tab: {t.get('title','')[:40]}")
                break
        if not xhs_tab:
            for t in tabs:
                url = t.get("url", "")
                if "xiaohongshu.com/explore/" in url:
                    xhs_tab = t
                    print(f"   Found other XHS tab: {t.get('title','')[:40]}")
                    break
    except Exception as e:
        print(f"   Error listing tabs: {e}")
    
    # Step 3: Navigate to note
    if xhs_tab:
        print("[3/7] Using existing tab, navigating to note...")
        page_id = xhs_tab["id"]
        ws_url = xhs_tab.get("webSocketDebuggerUrl", "")
        if not ws_url:
            ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}"
        
        ws = websocket.create_connection(ws_url, timeout=30)
        
        # Navigate
        cdp_send(ws, "Page.navigate", {"url": full_url})
        time.sleep(5)
        
        # Wait for load
        for _ in range(30):
            ready = eval_js(ws, "document.readyState", timeout=5)
            if ready == "complete":
                break
            time.sleep(0.5)
        
        time.sleep(3)
    else:
        print("[3/7] No XHS tab found, creating new tab...")
        tab = get_json(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(full_url)}")
        page_id = tab["id"]
        ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}"
        ws = websocket.create_connection(ws_url, timeout=30)
        time.sleep(8)
    
    # Step 4: Extract content
    print("[4/7] Extracting content...")
    
    title = eval_js(ws, "document.title")
    print(f"   Title: {title}")
    
    # Get description meta
    desc = eval_js(ws, """
        document.querySelector('meta[name="description"]')?.content || ''
    """)
    print(f"   Description: {desc[:200] if desc else 'N/A'}")
    
    # Get page text
    text = eval_js(ws, "document.body?.innerText?.substring(0, 20000) || ''")
    print(f"   Text length: {len(text) if text else 0}")
    
    # Get author
    author = eval_js(ws, """
        (()=>{
            const el = document.querySelector('.username, .name, [class*="user" i], [class*="author" i]');
            return el ? el.textContent?.trim() || '' : '';
        })()
    """)
    print(f"   Author: {author}")
    
    # Get likes
    likes = eval_js(ws, """
        (()=>{
            const els = Array.from(document.querySelectorAll('[class*=like], [class*=collect], [class*=comment]'));
            return els.map(e=>e.innerText?.trim()).filter(Boolean).join(' | ');
        })()
    """)
    
    ws.close()
    
    # Step 5: Print full content
    print("\n" + "=" * 60)
    print("FULL CONTENT:")
    print("=" * 60)
    if text:
        print(text[:5000])
    else:
        print("[No text extracted]")
    
    print("\n" + "=" * 60)
    print("LIKES/STATS:", likes)
    print("AUTHOR:", author)
    print("TITLE:", title)
    print("=" * 60)

if __name__ == "__main__":
    main()

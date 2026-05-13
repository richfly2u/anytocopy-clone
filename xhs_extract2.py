"""
Use existing XHS tab - navigate and extract content
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, time, re

CDP_PORT = 9223

def get_json(url):
    return json.loads(urllib.request.urlopen(url, timeout=10).read())

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
    
    # Find existing XHS tab
    print("[1/5] Finding existing XHS tab...")
    tabs = get_json(f"http://127.0.0.1:{CDP_PORT}/json")
    xhs_tab = None
    for t in tabs:
        url = t.get("url", "")
        if "xiaohongshu.com/explore/" in url:
            xhs_tab = t
            print(f"   Found: {t.get('url','')[:80]}")
            break
    
    if not xhs_tab:
        print("   No XHS tab found!")
        return
    
    page_id = xhs_tab["id"]
    ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}"
    ws = websocket.create_connection(ws_url, timeout=30)
    time.sleep(2)
    
    # First navigate to the short URL to resolve it
    print("[2/5] Navigating to short URL...")
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": short_url}}))
    time.sleep(8)
    
    url = eval_js(ws, "window.location.href")
    print(f"   URL: {url}")
    
    # Check if redirected to XHS
    if url and 'xiaohongshu.com' in url:
        # Extract note ID
        m = re.search(r'/explore/([a-f0-9]{24,32})', url)
        if m:
            note_id = m.group(1)
            print(f"   Note ID: {note_id}")
        
        # Get content
        print("[3/5] Extracting content...")
        time.sleep(3)
        
        # Wait for page to fully render
        for _ in range(20):
            ready = eval_js(ws, "document.readyState")
            if ready == "complete":
                break
            time.sleep(0.5)
        time.sleep(5)  # Extra wait for dynamic content
        
        title = eval_js(ws, "document.title")
        print(f"   Title: {title}")
        
        # Get note text content - try multiple selectors
        note_text = eval_js(ws, """
            (()=>{
                // Try different selectors for note content
                const selectors = [
                    '.note-content', '.note-text', '.content', 
                    '[class*="content"]', '[class*="note"]',
                    '.article', 'article'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim()) return el.innerText.trim();
                }
                // Fallback: get body text
                return document.body.innerText.substring(0, 10000);
            })()
        """)
        print(f"\n--- NOTE CONTENT ---\n{note_text[:3000]}")
        
        # Get author
        author = eval_js(ws, """
            (()=>{
                const el = document.querySelector('.username, .name, [class*="user" i], [class*="author" i]');
                return el ? el.textContent.trim() : '';
            })()
        """)
        print(f"\nAuthor: {author}")
        
        # Get stats
        stats = eval_js(ws, """
            (()=>{
                const els = Array.from(document.querySelectorAll('[class*=like], [class*=collect], [class*=comment], [class*=share]'));
                return els.map(e => e.innerText.trim()).filter(Boolean).join(' | ');
            })()
        """)
        print(f"Stats: {stats}")
        
        # Get video info
        has_video = eval_js(ws, """
            document.querySelector('video') !== null
        """)
        print(f"Has video: {has_video}")
        
    else:
        print(f"   Not redirected to XHS. URL: {url}")
        text = eval_js(ws, "document.body?.innerText?.substring(0, 2000) || ''")
        print(f"   Page text: {text}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

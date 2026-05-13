"""
Extract video from XHS note via CDP intercept
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, time, re

CDP_PORT = 9223
NOTE_URL = "https://www.xiaohongshu.com/explore/69f31df6000000003603182e?app_platform=android&ignoreEngage=true&app_version=9.27.0&share_from_user_hidden=true&xsec_source=app_share&type=video&xsec_token=CBlCHdlKgTIUKmIuLRiaXeJeTxU9Q8NJyGWdXUtKG_lFY=&author_share=1&shareRedId=ODhDNjxKSks2NzUyOTgwNjc8OTk8Sjo7&apptime=1778047798&share_id=9364262d2390463aacbe0d739c7cac9c&share_channel=copy_link&appuid=62a69efb0000000019028e42&xhsshare=CopyLink"

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
    # Find existing XHS tab
    print("[1/6] Finding XHS tab...")
    tabs = get_json(f"http://127.0.0.1:{CDP_PORT}/json")
    xhs_tab = None
    for t in tabs:
        url = t.get("url", "")
        if "xiaohongshu.com/explore/" in url:
            xhs_tab = t
            print(f"   Found: {url[:60]}...")
            break
    if not xhs_tab:
        print("❌ No XHS tab found!")
        return
    
    ws = websocket.create_connection(xhs_tab["webSocketDebuggerUrl"], timeout=30)
    time.sleep(1)
    
    # Enable Network
    print("[2/6] Enabling Network monitoring...")
    ws.send(json.dumps({"id": 1, "method": "Network.enable", "params": {}}))
    ws.send(json.dumps({"id": 2, "method": "Page.enable", "params": {}}))
    time.sleep(1)
    # Drain initial events
    for _ in range(30):
        try: ws.settimeout(0.1); ws.recv()
        except: break
    
    # Navigate to the note
    print("[3/6] Navigating to note page...")
    video_urls = set()
    image_urls = set()
    nav_started = False
    re_enabled = False
    
    ws.send(json.dumps({"id": 3, "method": "Page.navigate", "params": {"url": NOTE_URL}}))
    
    # Monitor network events
    print("[4/6] Intercepting network traffic (60s timeout)...")
    started = time.time()
    while time.time() - started < 60:
        try:
            ws.settimeout(0.5); raw = ws.recv()
        except: continue
        
        try:
            msg = json.loads(raw)
        except: continue
        
        method = msg.get("method", "")
        
        # Track navigation
        if method == "Page.frameStartedLoading":
            nav_started = True
            # Re-enable Network after navigation starts
            if not re_enabled:
                ws.send(json.dumps({"id": 100, "method": "Network.enable", "params": {}}))
                re_enabled = True
                print("   Network re-enabled after navigation")
        
        # Capture video responses
        if method == "Network.responseReceived":
            resp = msg["params"]["response"]
            url = resp.get("url", "")
            mime = resp.get("mimeType", "")
            
            # Video detection
            if "video" in mime and "xhscdn" in url:
                video_urls.add(url)
                print(f"   🎬 VIDEO: {url[:80]}...")
            
            # Also look for mp4 URLs
            if ".mp4" in url and "xhscdn" in url:
                video_urls.add(url)
                print(f"   🎬 MP4: {url[:80]}...")
            
            # Image detection (for reference)
            if "image" in mime and "xhscdn" in url and "avatar" not in url:
                image_urls.add(url)
        
        # Stop if page loaded and we have videos
        if method == "Page.frameStoppedLoading" and nav_started and video_urls:
            # Wait a bit more for any remaining responses
            time.sleep(3)
            # Drain remaining
            for _ in range(20):
                try: ws.settimeout(0.2); ws.recv()
                except: break
            break
    
    # Also try to get video URL from page JS
    print("\n[5/6] Getting video info from page...")
    video_src = eval_js(ws, """
        (()=>{
            const v = document.querySelector('video');
            if (v) {
                const src = v.currentSrc || v.src || '';
                const poster = v.poster || '';
                return JSON.stringify({src: src, poster: poster, duration: v.duration});
            }
            // Try to find video URL in page data
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                if (s.text && s.text.includes('video') && s.text.includes('url')) {
                    const m = s.text.match(/https?:\\/\\/[^\"'\\\\s]+\\.mp4[^\"'\\\\s]*/);
                    if (m) return 'found_in_script: ' + m[0];
                }
            }
            return 'no video element';
        })()
    """)
    print(f"   Video info: {video_src}")
    
    # Save video links to a file for the user
    print("\n[6/6] Results:")
    print("=" * 60)
    if video_urls:
        print(f"🎬 Found {len(video_urls)} video URL(s):")
        for i, v in enumerate(list(video_urls)[:3]):
            print(f"   {i+1}. {v}")
    else:
        print("❌ No video URLs intercepted")
    
    if image_urls:
        print(f"\n📸 Found {len(image_urls)} image(s)")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

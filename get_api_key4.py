"""
Reveal and get the Firebase API key
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
    tab_id = create_tab("https://console.cloud.google.com/apis/credentials?project=bentodish-alan")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(8)
    
    # Click "顯示金鑰" (Show key) for the Firebase browser key
    print("Clicking 顯示金鑰...")
    js(ws, """
        const allEls = document.querySelectorAll('span, button, a, div');
        for (const el of allEls) {
            if (el.innerText && el.innerText.trim() === '顯示金鑰') {
                el.click();
                return 'clicked';
            }
        }
        // Try alternative text
        for (const el of allEls) {
            if (el.innerText && el.innerText.includes('顯示')) {
                el.click();
                return 'clicked partial';
            }
        }
        return 'not found';
    """)
    time.sleep(3)
    
    # Now get the full text of the page to see the revealed key
    text = js(ws, "document.body.innerText")
    print(f"\nFull page text:\n{text}")
    
    # Extract AIzaSy keys from text
    keys = js(ws, """
        const allText = document.body.innerText;
        // Try different regex patterns for API keys
        const patterns = [
            /AIzaSy[A-Za-z0-9_-]{30,}/g,
            /[A-Za-z0-9_-]{35,40}/g
        ];
        const results = {};
        for (const p of patterns) {
            const matches = allText.match(p) || [];
            for (const m of matches) {
                results[m] = true;
            }
        }
        return JSON.stringify(Object.keys(results));
    """)
    print(f"\nKeys extracted: {keys}")
    
    ws.close()

if __name__ == "__main__":
    main()

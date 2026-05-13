"""
Get the full apiKey from DOM/JavaScript
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
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/settings/general")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(8)
    
    # Try to get the full config from various places
    # 1. Check for the config in a nearby element 
    # 2. Check React props
    # 3. Check the raw HTML source
    
    # Try to find the config code block
    code = js(ws, """
        // Find the code block containing the Firebase config
        const codeBlocks = document.querySelectorAll('code, pre');
        for (const block of codeBlocks) {
            const text = block.innerText;
            if (text.includes('apiKey')) {
                return text;
            }
        }
        return 'not found';
    """)
    print(f"Code block:\n{code}")
    
    # The apiKey might be in a hidden element or the full text before redaction
    # Try to get the raw HTML
    html = js(ws, """
        // Get the raw HTML of the config section
        const section = document.querySelector('.firebase-config, [data-testid*="config"], [data-testid*="sdk"]');
        if (section) return section.outerHTML.substring(0, 3000);
        return 'no section';
    """)
    print(f"\nHTML section:\n{html}")
    
    # Try accessing firebase SDK globals
    fb_config = js(ws, """
        try {
            // Check if firebase is initialized
            if (typeof firebase !== 'undefined') {
                const apps = firebase.apps;
                if (apps.length > 0) {
                    return JSON.stringify(apps[0].options);
                }
            }
        } catch(e) {}
        
        // Check global config objects
        try {
            // Some Firebase configs are stored in window.FIREBASE_CONFIG or similar
            for (const key of Object.keys(window)) {
                if (key.toLowerCase().includes('firebase') && typeof window[key] === 'object') {
                    const v = JSON.stringify(window[key]);
                    if (v.includes('apiKey')) return key + ': ' + v.substring(0, 500);
                }
            }
        } catch(e) {}
        
        return 'no config found';
    """)
    print(f"\nFirebase config from globals:\n{fb_config}")
    
    ws.close()

if __name__ == "__main__":
    main()

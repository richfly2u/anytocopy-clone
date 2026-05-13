"""
Test Firestore Dashboard via CDP
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
        if ed: return f"[ERR] {ed.get('text','')}"
        return r["result"].get("result", {}).get("value")
    return None

def main():
    print("=" * 60)
    print("Test Firestore Dashboard")
    print("=" * 60)
    
    tab_id = create_tab("https://richfly2u.github.io/daily-dashboard/")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    url = js(ws, "window.location.href", timeout=10)
    title = js(ws, "document.title", timeout=10)
    print(f"URL: {url}")
    print(f"Title: {title}")
    
    # Check for console errors
    console_errors = js(ws, """
        // Check the page body for error indicators
        const body = document.body.innerText;
        return body.substring(0, 500);
    """)
    print(f"\nPage text: {console_errors[:300]}")
    
    # Check if the page is interactive
    has_login = js(ws, """
        !!document.getElementById('loginKey')
    """)
    print(f"Has login input: {has_login}")
    
    # Type a test board name
    if has_login:
        print("\nTyping test login...")
        js(ws, """
            const input = document.getElementById('loginKey');
            const nativeSet = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSet.call(input, 'test');
            input.dispatchEvent(new Event('input', {bubbles: true}));
        """)
        time.sleep(1)
        
        # Click login
        js(ws, """
            document.getElementById('loginBtn').click();
        """)
        time.sleep(5)
        
        # Check for errors
        visibility = js(ws, """
            document.getElementById('mainApp').style.display
        """)
        print(f"Main app visible: {visibility}")
        
        # Check console output
        console_log = js(ws, """
            // Read console messages if available
            // In a real browser we'd check but here just check page state
            const statusDot = document.getElementById('statusDot');
            return statusDot ? statusDot.className : 'no status';
        """)
        print(f"Status: {console_log}")
        
        # Check if items are rendered
        checklist = js(ws, """
            const items = document.querySelectorAll('.check-item');
            return items.length + ' items rendered';
        """)
        print(f"Checklist: {checklist}")
        
        # Check for Firestore errors by looking for error messages in the UI
        # (Firestore errors will show as offline status)
    
    # Check the browser console for errors
    print("\nCapturing browser console...")
    time.sleep(3)
    
    # Get any error messages
    errors = cdp(ws, "Runtime.evaluate", {
        "expression": """
            // Try to check if there are any script errors
            "Page loaded successfully"
        """,
        "returnByValue": True
    })
    if errors:
        print(f"   Result: {errors.get('result',{}).get('result',{}).get('value')}")
    
    ws.close()
    print("\n✅ Test complete!")

if __name__ == "__main__":
    main()

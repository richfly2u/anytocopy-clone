"""
Debug JS errors in the dashboard
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
        if ed: return {"error": ed.get('text',''), "stack": ed.get('stackTrace',{})}
        return {"value": r["result"].get("result", {}).get("value")}
    return {"error": "no result"}

def get_console(ws):
    """Get console messages via Page.getConsoleMessages"""
    r = cdp(ws, "Runtime.evaluate", {
        "expression": """
            // Get errors from the page
            (window.__hermesErrors || []).join('\\n')
        """,
        "returnByValue": True
    })
    return r

def main():
    print("=" * 60)
    print("Debug Dashboard Errors")
    print("=" * 60)
    
    # Enable Console domain to capture messages
    tab_id = create_tab("https://richfly2u.github.io/daily-dashboard/")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Enable console
    cdp(ws, "Console.enable")
    
    # Type login
    js(ws, """
        const input = document.getElementById('loginKey');
        const nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSet.call(input, 'test');
        input.dispatchEvent(new Event('input', {bubbles: true}));
    """)
    time.sleep(1)
    
    js(ws, "document.getElementById('loginBtn').click()")
    time.sleep(8)
    
    # Now check the page for errors
    print("\nChecking for errors...")
    
    # Check if status dot element exists
    el = js(ws, "document.getElementById('statusDot') !== null")
    print(f"Status dot exists: {el}")
    
    # Check if checklist exists
    el2 = js(ws, "document.getElementById('checklist') !== null")
    print(f"Checklist element exists: {el2}")
    
    # Check what's rendered
    rendered = js(ws, "document.getElementById('checklist')?.innerHTML?.substring(0, 200)")
    print(f"Checklist HTML: {rendered}")
    
    # Try to catch the error by wrapping in try/catch
    error_check = js(ws, """
        try {
            const statusDot = document.getElementById('statusDot');
            const cls = statusDot ? statusDot.className : 'missing';
            return 'status=' + cls;
        } catch(e) {
            return 'ERROR: ' + e.message;
        }
    """)
    print(f"Error check: {error_check}")
    
    # Check if the error is a module type issue (type="module" not supported?)
    module_check = js(ws, """
        const scripts = document.querySelectorAll('script');
        return Array.from(scripts).map(s => s.type || 'no-type').join(', ');
    """)
    print(f"Script types: {module_check}")
    
    # Check for any visible error text on the page
    page_text = js(ws, "document.body.innerText?.substring(0, 1000)")
    print(f"\nPage text:\n{page_text}")
    
    # Try to get Firestore error
    fb_error = js(ws, """
        // Check if there's a visible error from Firebase
        const body = document.body.innerText;
        if (body.includes('Error') || body.includes('error')) return 'has error text';
        // Check console log content
        return 'no visible error';
    """)
    print(f"\nError check: {fb_error}")
    
    # Check if the module script ran at all
    script_ran = js(ws, """
        typeof window.DEFAULTS !== 'undefined'
    """)
    print(f"DEFAULTS defined: {script_ran}")
    
    ws.close()

if __name__ == "__main__":
    main()

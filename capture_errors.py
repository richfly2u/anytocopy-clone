"""
Get actual console error messages
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
        if ed:
            stack = ed.get('stackTrace', {}).get('callFrames', [])
            stack_str = '\\n'.join([f"  {f.get('functionName','?')} at {f.get('url','?')}:{f.get('lineNumber','?')}" for f in stack[:5]])
            return f"ERROR: {ed.get('text','')}\\n{stack_str}"
        val = r["result"].get("result", {}).get("value")
        if val is None:
            return "null/undefined"
        return val
    return "no_result"

def main():
    print("=" * 60)
    print("Capture Console Errors")
    print("=" * 60)
    
    tab_id = create_tab("https://richfly2u.github.io/daily-dashboard/")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    
    # Enable console and page domains
    cdp(ws, "Console.enable")
    cdp(ws, "Runtime.enable")
    cdp(ws, "Page.enable")
    time.sleep(3)
    
    # Collect any console messages that were already emitted
    print("Collecting initial messages...")
    
    # Navigate to clear and reload
    cdp(ws, "Page.navigate", {"url": "https://richfly2u.github.io/daily-dashboard/"})
    time.sleep(5)
    
    # Intercept messages
    collected = []
    for _ in range(20):  # Try 20 times
        try:
            ws.settimeout(0.5)
            raw = ws.recv()
            msg = json.loads(raw)
            method = msg.get("method", "")
            if method == "Console.messageAdded":
                m = msg["params"]["message"]
                collected.append(f"[{m['level']}] {m['text']}")
            elif method == "Runtime.exceptionThrown":
                exc = msg["params"]["exceptionDetails"]
                collected.append(f"[EXCEPTION] {exc.get('text','')} at line {exc.get('lineNumber','?')}")
            elif method == "Runtime.consoleAPICalled":
                args = msg["params"]["args"]
                texts = [a.get('value', str(a)) for a in args]
                collected.append(f"[CONSOLE] {' '.join(str(t) for t in texts)}")
        except websocket.WebSocketTimeoutException:
            pass
    
    print(f"\nCollected {len(collected)} messages:")
    for c in collected:
        print(f"  {c}")
    
    # Now trigger the error
    print("\nTyping login and clicking...")
    js(ws, """
        const input = document.getElementById('loginKey');
        const nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSet.call(input, 'test2');
        input.dispatchEvent(new Event('input', {bubbles: true}));
    """)
    time.sleep(1)
    
    js(ws, "document.getElementById('loginBtn').click()")
    time.sleep(8)
    
    # Collect more messages
    for _ in range(20):
        try:
            ws.settimeout(0.5)
            raw = ws.recv()
            msg = json.loads(raw)
            method = msg.get("method", "")
            if method == "Console.messageAdded":
                m = msg["params"]["message"]
                collected.append(f"[{m['level']}] {m['text']}")
            elif method == "Runtime.exceptionThrown":
                exc = msg["params"]["exceptionDetails"]
                desc = exc.get('text','')
                stack = exc.get('stackTrace',{})
                frames = stack.get('callFrames',[])
                stack_str = ' | '.join([f"{f.get('functionName','?')}:{f.get('lineNumber','?')}" for f in frames[:3]])
                collected.append(f"[EXCEPTION] {desc} [{stack_str}]")
            elif method == "Runtime.consoleAPICalled":
                args = msg["params"]["args"]
                texts = [str(a.get('value', str(a))) for a in args]
                collected.append(f"[CONSOLE] {' '.join(texts)}")
        except websocket.WebSocketTimeoutException:
            pass
    
    print("\nFinal collected messages:")
    for c in collected[-30:]:  # Last 30
        print(f"  {c}")
    
    ws.close()

if __name__ == "__main__":
    main()

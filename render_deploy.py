"""
Deploy backend to Render via GitHub login
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time, re

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
            if exc: print(f"[JS WARN] {exc.get('text', str(exc))}"); return None
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def click_by_text(ws, text, tag="button"):
    """Click an element by its text content"""
    return evaluate(ws, f"""
        (() => {{
            const items = Array.from(document.querySelectorAll('{tag}'));
            const target = items.find(el => el.innerText.trim() === {json.dumps(text)});
            if (target) {{ target.click(); return 'clicked: ' + {json.dumps(text)}; }}
            // Try contains
            const target2 = items.find(el => el.innerText.trim().includes({json.dumps(text)}));
            if (target2) {{ target2.click(); return 'clicked(partial): ' + {json.dumps(text)}; }}
            return 'not found: ' + {json.dumps(text)};
        }})()
    """)

def wait_for_nav(ws, timeout=60):
    """Wait for navigation to complete"""
    start = time.time()
    while time.time() - start < timeout:
        state = evaluate(ws, "document.readyState", timeout=5)
        if state == "complete":
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False

def type_react_input(ws, sel, value):
    """Type into React input using native value setter"""
    return evaluate(ws, f"""
        (() => {{
            const inp = document.querySelector({json.dumps(sel)});
            if (!inp) {{ return 'not found: ' + {json.dumps(sel)}; }}
            inp.focus();
            const nativeSet = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeSet.call(inp, {json.dumps(value)});
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
            inp.dispatchEvent(new Event('blur'));
            return 'typed: ' + {json.dumps(value)};
        }})()
    """)

def main():
    print("=" * 60)
    print("Deploy Backend to Render")
    print("=" * 60)
    
    # Step 1: Go to Render login
    print("[1/5] Opening Render login...")
    tab_id = create_tab("https://dashboard.render.com/login")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    wait_for_nav(ws)
    time.sleep(2)
    
    # Step 2: Click GitHub login
    print("[2/5] Clicking GitHub login...")
    result = click_by_text(ws, "GitHub")
    print(f"   {result}")
    time.sleep(3)
    wait_for_nav(ws)
    time.sleep(3)
    
    # Check where we are now
    url = evaluate(ws, "window.location.href", timeout=10)
    title = evaluate(ws, "document.title", timeout=10)
    print(f"   URL: {url}")
    print(f"   Title: {title}")
    
    body_text = evaluate(ws, "document.body.innerText?.substring(0, 1000)", timeout=10)
    print(f"   Body: {body_text}")
    
    # If GitHub authorization page
    if "authorize" in url.lower() or "oauth" in url.lower() or "authorize" in (body_text or "").lower():
        print("[3/5] Authorizing Render on GitHub...")
        # Look for Authorize button
        result = click_by_text(ws, "Authorize", "button")
        print(f"   {result}")
        time.sleep(3)
        wait_for_nav(ws)
        time.sleep(3)
    
    # Check if we're on Render dashboard now
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   After auth URL: {url}")
    
    if "render.com" in url:
        print("[3/5] Logged into Render!")
        
        # Step 3: Go to Blueprint deploy (New + → Blueprint)
        print("[4/5] Starting Blueprint deploy...")
        evaluate(ws, f"""
            window.location.href = 'https://dashboard.render.com/select-repo?type=blueprint'
        """)
        time.sleep(3)
        wait_for_nav(ws)
        time.sleep(3)
        
        url2 = evaluate(ws, "window.location.href", timeout=10)
        print(f"   Blueprint URL: {url2}")
        body2 = evaluate(ws, "document.body.innerText?.substring(0, 1500)", timeout=10)
        print(f"   Body: {body2}")
        
        # Look for our repo
        result = click_by_text(ws, "richfly2u/daily-dashboard", "span, div, a, button")
        print(f"   Select repo: {result}")
        time.sleep(3)
        wait_for_nav(ws)
        time.sleep(3)
        
        url3 = evaluate(ws, "window.location.href", timeout=10)
        print(f"   After repo select: {url3}")
        body3 = evaluate(ws, "document.body.innerText?.substring(0, 2000)", timeout=10)
        print(f"   Body: {body3}")
        
        # Step 4: Configure the Blueprint
        print("[5/5] Looking for deploy/connect button...")
        
        # Check what's on the page
        all_btns = evaluate(ws, """
            JSON.stringify(Array.from(document.querySelectorAll('button, a, [role="button"]')).map(el => ({
                text: (el.innerText || '').trim().substring(0, 40),
                tag: el.tagName + (el.id ? '#' + el.id : ''),
                href: (el.getAttribute('href') || '').substring(0, 40)
            })))
        """)
        print(f"   Buttons: {all_btns}")
        
        # Click Connect / Deploy Blueprint
        for btn_text in ["Connect", "Deploy Blueprint", "Deploy", "Connect repository", "Next"]:
            result = click_by_text(ws, btn_text)
            if "clicked" in str(result):
                print(f"   {result}")
                time.sleep(3)
                wait_for_nav(ws)
                time.sleep(3)
                break
        
        # Final URL
        final_url = evaluate(ws, "window.location.href", timeout=10)
        final_title = evaluate(ws, "document.title", timeout=10)
        final_body = evaluate(ws, "document.body.innerText?.substring(0, 1500)", timeout=10)
        print(f"\n   Final URL: {final_url}")
        print(f"   Final Title: {final_title}")
        print(f"   Body: {final_body}")
        
        # Try to get the service URL
        service_url = evaluate(ws, """
            (() => {
                const links = document.querySelectorAll('a');
                for (const link of links) {
                    if (link.href && link.href.includes('onrender.com')) {
                        return link.href;
                    }
                }
                return null;
            })()
        """)
        print(f"   Service URL: {service_url}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

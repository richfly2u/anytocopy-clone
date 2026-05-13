"""
Deploy to Render - retry with free plan
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

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
    return evaluate(ws, f"""
        (() => {{
            const items = Array.from(document.querySelectorAll('{tag}'));
            let target = items.find(el => el.innerText.trim() === {json.dumps(text)});
            if (target) {{ target.click(); return 'clicked: ' + {json.dumps(text)}; }}
            target = items.find(el => el.innerText.trim().includes({json.dumps(text)}));
            if (target) {{ target.click(); return 'clicked(partial): ' + {json.dumps(text)}; }}
            return 'not found: ' + {json.dumps(text)};
        }})()
    """)

def wait_for_nav(ws, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        state = evaluate(ws, "document.readyState", timeout=5)
        if state == "complete":
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False

def type_react_input(ws, sel, value):
    return evaluate(ws, f"""
        (() => {{
            const inp = document.querySelector({json.dumps(sel)});
            if (!inp) return 'not found: ' + {json.dumps(sel)};
            inp.focus();
            const nativeSet = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeSet.call(inp, {json.dumps(value)});
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
            inp.dispatchEvent(new Event('blur'));
            return 'typed';
        }})()
    """)

def main():
    print("=" * 60)
    print("Deploy to Render - Free Plan")
    print("=" * 60)
    
    # Go directly to select-repo page
    print("[1/5] Opening Render Blueprint...")
    tab_id = create_tab("https://dashboard.render.com/select-repo?type=blueprint")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    wait_for_nav(ws)
    time.sleep(3)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL: {url}")
    
    # If redirected to login, we need to log in via GitHub
    if "login" in url:
        print("[!] Not logged in. Clicking GitHub login...")
        click_by_text(ws, "GitHub")
        time.sleep(3)
        wait_for_nav(ws)
        time.sleep(3)
        
        # Check for authorize page
        url2 = evaluate(ws, "window.location.href", timeout=10)
        body = evaluate(ws, "document.body.innerText?.substring(0, 500)", timeout=10)
        print(f"   After GitHub: {url2}")
        
        if "authorize" in (body or "").lower() or "authorize" in url2.lower():
            click_by_text(ws, "Authorize", "button")
            time.sleep(3)
            wait_for_nav(ws)
            time.sleep(3)
        
        # Navigate again
        evaluate(ws, "window.location.href = 'https://dashboard.render.com/select-repo?type=blueprint'")
        time.sleep(3)
        wait_for_nav(ws)
        time.sleep(3)
    
    # Find and click "Connect" on daily-dashboard
    print("[2/5] Connecting daily-dashboard repo...")
    repo_connect = evaluate(ws, """
        (() => {
            const connectBtns = Array.from(document.querySelectorAll('button'));
            // Find the row with daily-dashboard and click its Connect button
            const rows = document.querySelectorAll('[data-testid*="repo"], div:has(a[href*="daily-dashboard"])');
            for (const row of rows) {
                const btn = row.querySelector('button');
                if (btn && btn.innerText.trim() === 'Connect') {
                    btn.click();
                    return 'clicked Connect for daily-dashboard';
                }
            }
            // Fallback: find all Connect buttons and click the first one whose sibling/preceding text includes daily-dashboard
            const btns = Array.from(document.querySelectorAll('button'));
            for (let i = 0; i < btns.length; i++) {
                if (btns[i].innerText.trim() === 'Connect') {
                    const parent = btns[i].closest('div');
                    if (parent && parent.innerText.includes('daily-dashboard')) {
                        btns[i].click();
                        return 'clicked via parent check';
                    }
                }
            }
            // Direct click on the "richfly2u / daily-dashboard" link then find Connect
            const link = document.querySelector('a[href*="daily-dashboard"]');
            if (link) {
                const row = link.closest('div');
                if (row) {
                    const btn = row.querySelector('button');
                    if (btn) { btn.click(); return 'clicked via link parent'; }
                }
            }
            return 'not found';
        })()
    """)
    print(f"   {repo_connect}")
    time.sleep(3)
    wait_for_nav(ws)
    time.sleep(3)
    
    url = evaluate(ws, "window.location.href", timeout=10)
    print(f"   URL: {url}")
    
    # Step 3: Fill Blueprint name and check for issues
    print("[3/5] Setting up Blueprint...")
    body = evaluate(ws, "document.body.innerText?.substring(0, 2000)", timeout=10)
    print(f"   Body: {body}")
    
    # Check if there's a payment dialog
    dialog = evaluate(ws, """
        document.querySelector('[role="dialog"], [role="alertdialog"], .ReactModalPortal, [data-testid*="modal"]') !== null
    """)
    print(f"   Payment dialog visible: {dialog}")
    
    if dialog:
        # Try to dismiss/cancel the payment dialog
        clicked = click_by_text(ws, "Cancel")
        print(f"   Dismiss dialog: {clicked}")
        time.sleep(2)
    
    # Find and fill Blueprint Name
    result = type_react_input(ws, "input[name='name'], input[placeholder*='Blueprint'], input[placeholder*='blueprint']", "daily-dashboard-blueprint")
    print(f"   Name field: {result}")
    
    # Click Review / Deploy Blueprint button
    print("[4/5] Deploying Blueprint...")
    for btn_text in ["Review configuration", "Review", "Deploy Blueprint", "Create Blueprint", "Deploy"]:
        result = click_by_text(ws, btn_text)
        if "clicked" in str(result):
            print(f"   {result}")
            time.sleep(3)
            wait_for_nav(ws)
            time.sleep(5)
            break
    
    # Check for another payment dialog
    body2 = evaluate(ws, "document.body.innerText?.substring(0, 2000)", timeout=10)
    print(f"   Body after deploy: {body2}")
    
    # Try to confirm / deploy
    for btn_text in ["Create Blueprint", "Deploy", "Confirm", "Start deploy"]:
        result = click_by_text(ws, btn_text, "button, span, a")
        if "clicked" in str(result):
            print(f"   {result}")
            time.sleep(3)
            wait_for_nav(ws)
            time.sleep(5)
            break
    
    print("[5/5] Fetching service URL...")
    time.sleep(5)
    body3 = evaluate(ws, "document.body.innerText?.substring(0, 2000)", timeout=10)
    print(f"   Final body: {body3}")
    
    # Check for the service URL
    service_url = evaluate(ws, """
        (() => {
            const links = document.querySelectorAll('a[href*="onrender.com"]');
            if (links.length > 0) return links[0].href;
            // Check page text for URLs
            const text = document.body.innerText;
            const match = text.match(/https?:\\/\\/[a-z0-9-]+\\.onrender\\.com/);
            return match ? match[0] : null;
        })()
    """)
    print(f"   Service URL: {service_url}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

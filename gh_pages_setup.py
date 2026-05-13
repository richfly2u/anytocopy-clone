"""
Enable GitHub Pages via CDP
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket
import json
import urllib.request
import urllib.parse
import time

CDP_PORT = 9223

def evaluate(ws, expr, timeout=10):
    msg_id = int(time.time() * 1000) % 1000000
    msg = {"id": msg_id, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": True
    }}
    ws.send(json.dumps(msg))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(1.0)
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if resp.get("id") == msg_id:
            exc = resp.get("result", {}).get("exceptionDetails")
            if exc:
                print(f"[JS ERROR] {exc.get('text', str(exc))}")
                return None
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def wait_for_page(ws, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        state = evaluate(ws, "document.readyState", timeout=5)
        if state == "complete":
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False

def create_tab(url):
    req = urllib.request.Request(
        f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}",
        method="PUT"
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())["id"]

def main():
    print("=" * 60)
    print("Enable GitHub Pages via CDP")
    print("=" * 60)
    
    # Navigate to repo pages settings
    tab_id = create_tab("https://github.com/richfly2u/daily-dashboard/settings/pages")
    page_ws = websocket.create_connection(
        f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30
    )
    print("[1/4] Loading Pages settings...")
    wait_for_page(page_ws)
    time.sleep(3)
    
    url = evaluate(page_ws, "window.location.href", timeout=10)
    title = evaluate(page_ws, "document.title", timeout=10)
    print(f"   URL: {url}")
    print(f"   Title: {title}")
    
    # Check if Pages is already configured
    body_text = evaluate(page_ws, "document.body?.innerText?.substring(0, 1000)", timeout=10)
    print(f"   Page text: {body_text}")
    
    # Look for the "Deploy from a branch" section and set it up
    # GitHub Pages settings has a "Branch" section with a source selector
    
    # Try clicking the branch dropdown or the "None" / branch selector
    print("[2/4] Looking for branch source setting...")
    
    # Check if there's a "Save" button (means Pages is not yet configured)
    has_save = evaluate(page_ws, """
        document.body.innerText.includes('Save') || false
    """, timeout=10)
    print(f"   Has 'Save' on page: {has_save}")
    
    # Check for "Deploy from a branch" or similar text
    has_deploy_branch = evaluate(page_ws, """
        document.body.innerText.includes('Deploy from a branch') || 
        document.body.innerText.includes('Branch:') ||
        document.body.innerText.includes('Your site is live at') || false
    """, timeout=10)
    print(f"   Has deploy settings: {has_deploy_branch}")
    
    # Try different approaches based on what we see
    # Option 1: Look for the "Branch" dropdown/select
    # Option 2: Look for a "Save" button meaning we need to configure
    
    # Let's find all interactive elements related to Pages setup
    pages_form = evaluate(page_ws, """
        (() => {
            const btns = Array.from(document.querySelectorAll('button, summary, select'));
            return JSON.stringify(btns.map(b => ({
                text: (b.innerText || '').trim().substring(0, 50),
                type: b.tagName + (b.type ? '[' + b.type + ']' : ''),
                role: b.getAttribute('role') || '',
                'data-name': b.getAttribute('data-name') || ''
            })));
        })()
    """, timeout=10)
    print(f"   Buttons: {pages_form}")
    
    # Check if "Your site is live at" is on the page
    site_live = evaluate(page_ws, """
        document.body.innerText.includes('Your site is live at') || 
        document.body.innerText.includes('Pages settings') || false
    """, timeout=10)
    print(f"   Site already live: {site_live}")
    
    # If site is already live, get the URL
    if site_live:
        site_url = evaluate(page_ws, """
            (() => {
                const el = document.querySelector('a[href*="github.io"]');
                return el ? el.href : null;
            })()
        """, timeout=10)
        print(f"   Site URL: {site_url}")
    
    print()
    print("[3/4] Looking for the branch source selector...")
    
    # Try to find and click the branch selector
    # In the new GitHub UI, there might be a "None" or a branch dropdown
    clicked_branch = evaluate(page_ws, """
        (() => {
            // Try common selectors for the Pages branch source
            const selectors = [
                'summary[data-menu-button]',
                'button[aria-label*="branch"]',
                'button[aria-label*="Branch"]',
                'summary:has(span:contains("None"))',
                'summary:has(span:contains("Branch"))',
                'select[name*="branch"]',
                'button:contains("master")',
                'button:contains("main")',
                'button:contains("None")',
            ];
            for (const sel of selectors) {
                try {
                    const el = document.querySelector(sel);
                    if (el) { el.click(); return 'clicked: ' + sel; }
                } catch(e) {}
            }
            return 'no branch selector found';
        })()
    """, timeout=10)
    print(f"   {clicked_branch}")
    time.sleep(2)
    
    # If we clicked a dropdown, look for master/main in the menu
    menu_items = evaluate(page_ws, """
        (() => {
            const items = document.querySelectorAll('[role="menuitem"], [role="option"], li a, li button');
            return JSON.stringify(Array.from(items).map(i => ({
                text: (i.innerText || '').trim().substring(0, 30),
                href: (i.getAttribute('href') || '').substring(0, 30)
            })));
        })()
    """, timeout=10)
    print(f"   Menu items: {menu_items}")
    
    # Try clicking master branch if in menu
    if menu_items and 'master' in menu_items:
        evaluate(page_ws, """
            document.querySelector('[role="menuitem"] a, [role="option"]')?.click();
        """, timeout=5)
        time.sleep(1)
    
    # Try the root folder selector (GitHub Pages default is /root or /docs)
    print("[4/4] Configuring source as main branch, root folder...")
    
    # In the new UI, there might be a "Save" button
    saved = evaluate(page_ws, """
        (() => {
            const saveBtn = Array.from(document.querySelectorAll('button'))
                .find(b => b.innerText.trim() === 'Save' && !b.disabled);
            if (saveBtn) { saveBtn.click(); return 'saved'; }
            
            // Alternative: look for any primary/submit button
            const primary = document.querySelector('button[type="submit"].btn-primary, .btn-primary');
            if (primary) { primary.click(); return 'clicked primary'; }
            
            return 'no save button';
        })()
    """, timeout=10)
    print(f"   Save result: {saved}")
    
    time.sleep(5)
    wait_for_page(page_ws)
    
    # Final check
    final_url = evaluate(page_ws, "window.location.href", timeout=10)
    final_text = evaluate(page_ws, "document.body?.innerText?.substring(0, 500)", timeout=10)
    print(f"\n   Final URL: {final_url}")
    print(f"   Page text: {final_text}")
    
    # Check for Pages URL
    pages_url = evaluate(page_ws, """
        (() => {
            const links = document.querySelectorAll('a');
            for (const link of links) {
                if (link.href && link.href.includes('github.io')) {
                    return link.href;
                }
            }
            // Also check for the Visit site button area
            const text = document.body.innerText;
            const match = text.match(/https?:\\/\\/[^\\s]+\\.github\\.io[^\\s]*/);
            return match ? match[0] : null;
        })()
    """, timeout=10)
    print(f"   GitHub Pages URL: {pages_url}")
    
    page_ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

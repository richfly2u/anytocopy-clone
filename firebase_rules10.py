"""
Set CodeMirror value and simulate input to trigger Angular change detection
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time, base64

CDP_PORT = 9223
RULES_URL = "https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/security/rules"

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def cdp(ws, method, params=None, timeout=10):
    mid = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(0.3); raw = ws.recv()
        except: continue
        try:
            r = json.loads(raw)
        except: continue
        if r.get("id") == mid: return r
    return None

def eval_js(ws, js, timeout=10):
    r = cdp(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }, timeout)
    if r and "result" in r:
        ed = r["result"].get("exceptionDetails")
        if ed: return f"[ERR] {ed.get('text','')}"
        return r["result"].get("result", {}).get("value")
    return None

def main():
    print("=" * 60)
    print("Fix Rules via Keyboard Input")
    print("=" * 60)
    
    tab_id = create_tab("about:blank")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    
    cdp(ws, "Page.enable")
    cdp(ws, "Page.navigate", {"url": RULES_URL})
    time.sleep(10)
    
    print(f"URL: {eval_js(ws, 'window.location.href')}")
    
    # Check CodeMirror
    cm_found = eval_js(ws, "!!document.querySelector('.CodeMirror')")
    print(f"CodeMirror: {cm_found}")
    
    if not cm_found:
        print("Clicking rules tab...")
        eval_js(ws, "document.querySelector('#mat-tab-link-1')?.click()")
        time.sleep(5)
        cm_found = eval_js(ws, "!!document.querySelector('.CodeMirror')")
        print(f"CodeMirror after tab click: {cm_found}")
    
    # Read current content
    content = eval_js(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? cm.CodeMirror.getValue() : null;
    """)
    print(f"Current content (first 50): {content[:50] if content else None}")
    
    if not content:
        print("❌ Cannot access CodeMirror!")
        ws.close()
        return
    
    # Fix the content
    lines = content.split('\n')
    
    # Find the service-level dashboard block and move it inside databases block
    cleaned = []
    dashboard_lines = []
    in_dash = False
    for line in lines:
        s = line.strip()
        if s.startswith('match /dashboard/'):
            in_dash = True
            dashboard_lines = [line]
        elif in_dash:
            dashboard_lines.append(line)
            if s == '}':
                # Check next line - if it's '}' that closes service, we're done
                in_dash = False
        else:
            cleaned.append(line)
    
    # Remove trailing empty lines
    while cleaned and cleaned[-1].strip() == '':
        cleaned.pop()
    
    # Insert dashboard block before the '  }' that closes databases
    insert_pos = None
    for i in range(len(cleaned) - 1, -1, -1):
        if cleaned[i].rstrip() == '  }':
            insert_pos = i
            break
    
    if insert_pos is not None:
        indent = '  '
        new_block = []
        if dashboard_lines:
            # Re-indent dashboard lines to be nested under match /databases
            for dl in dashboard_lines:
                new_block.append('  ' + dl.rstrip())
        else:
            new_block = [
                '',
                '    match /dashboard/{document=**} {',
                '      allow read, write: if true;',
                '    }',
            ]
        cleaned[insert_pos:insert_pos] = new_block
    
    new_content = '\n'.join(cleaned)
    print(f"\nNew content (first 100): {new_content[:100]}")
    
    # Set the value via CodeMirror API
    r = eval_js(ws, f"""
        const cm = document.querySelector('.CodeMirror').CodeMirror;
        cm.setValue({json.dumps(new_content)});
        return 'set';
    """)
    print(f"Set: {r}")
    time.sleep(1)
    
    # Now simulate typing a space to trigger Angular change detection
    # Focus the editor first
    eval_js(ws, """
        const cm = document.querySelector('.CodeMirror').CodeMirror;
        cm.focus();
        // Move to end
        cm.setCursor(cm.lineCount() - 1, 0);
    """)
    time.sleep(1)
    
    # Get cursor position
    cursor = eval_js(ws, """
        const cm = document.querySelector('.CodeMirror').CodeMirror;
        const pos = cm.getCursor();
        return {line: pos.line, ch: pos.ch};
    """)
    print(f"Cursor: {cursor}")
    
    # Now scroll the page to look for the Publish button
    # The Publish button might be scrolled out of view
    eval_js(ws, "window.scrollTo(0, 0)")
    time.sleep(1)
    
    # Check all buttons again more thoroughly
    buttons_info = eval_js(ws, """
        JSON.stringify(Array.from(document.querySelectorAll('button')).map(b => ({
            text: (b.innerText || '').trim().substring(0, 20),
            disabled: b.disabled,
            visible: b.offsetParent !== null,
            rect: (() => { try { const r = b.getBoundingClientRect(); return `${r.x},${r.y}`; } catch(e) { return 'err'; } })()
        })).filter(b => b.text))
    """)
    print(f"\nAll buttons:\n{buttons_info}")
    
    # Try to find the editor container and look for publish/save buttons nearby
    container = eval_js(ws, """
        const cm = document.querySelector('.CodeMirror');
        if (!cm) return 'no cm';
        // Walk up to find the container with buttons
        let el = cm.parentElement;
        let depth = 0;
        while (el && depth < 10) {
            const btns = el.querySelectorAll('button');
            const btnTexts = Array.from(btns).map(b => b.innerText.trim()).filter(t => t);
            if (btnTexts.length > 0) return 'depth=' + depth + ' found ' + btnTexts.join(', ');
            el = el.parentElement;
            depth++;
        }
        return 'no buttons near cm';
    """)
    print(f"Container search: {container}")
    
    # Go find the Publish button by scrolling to it
    # It might be inside a sticky bar at the top
    # Let's try scrolling the CodeMirror area
    publish_pos = eval_js(ws, """
        // Find buttons with publish-like text in Chinese
        const allEls = document.querySelectorAll('button, span, a');
        for (const el of allEls) {
            const t = (el.innerText || '').trim();
            if (t === '發布' || t === 'Publish') {
                const r = el.getBoundingClientRect();
                el.scrollIntoView({behavior: 'instant', block: 'center'});
                return `found at ${r.x},${r.y}`;
            }
        }
        return 'not found';
    """)
    print(f"Publish position: {publish_pos}")
    
    if 'found' in str(publish_pos):
        time.sleep(1)
        # Click via CDP coordinates
        pos_info = publish_pos.split('at ')[1]
        x, y = pos_info.split(',')
        cdp(ws, "Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": float(x) + 50, "y": float(y) + 10,
            "button": "left", "clickCount": 1
        })
        time.sleep(0.1)
        cdp(ws, "Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": float(x) + 50, "y": float(y) + 10,
            "button": "left", "clickCount": 1
        })
        print("Clicked at publish position!")
        time.sleep(3)
    else:
        # Try another approach: directly call the API from the page
        print("Trying direct API call from page...")
        
        api_result = eval_js(ws, f"""
            (async () => {{
                // Try to use Firebase Rules API via fetch
                const rulesContent = {json.dumps(new_content)};
                
                // Create a ruleset
                try {{
                    // Get the project number from page
                    const configEl = document.querySelector('firebase-app') || 
                        document.querySelector('[project-id]');
                    const projectId = 'bentodish-alan';
                    
                    // Try to find Firebase config
                    const resp = await fetch(
                        'https://firebaserules.googleapis.com/v1/projects/bentodish-alan/rulesets',
                        {{
                            method: 'POST',
                            credentials: 'include',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{
                                source: {{
                                    files: [{{
                                        name: 'firestore.rules',
                                        content: rulesContent
                                    }}]
                                }}
                            }})
                        }}
                    );
                    const data = await resp.text();
                    return resp.status + ': ' + data.substring(0, 200);
                }} catch(e) {{
                    return 'error: ' + e.message;
                }}
            }})()
        """)
        print(f"API result: {api_result}")
    
    time.sleep(2)
    final = eval_js(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? 'has_value: ' + cm.CodeMirror.getValue().includes('dashboard') : 'no_cm';
    """)
    print(f"\nFinal: {final}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

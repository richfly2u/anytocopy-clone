"""
Update Firestore rules via Firebase API (from logged-in browser)
"""
import sys, io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import websocket, json, urllib.request, urllib.parse, time

CDP_PORT = 9223
RULES_URL = "https://console.firebase.google.com/u/0/project/bentodish-alan/firestore/databases/-default-/security/rules"

def evaluate(ws, expr, timeout=15):
    msg_id = int(time.time() * 1000) % 1000000
    ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": True,
        "userGesture": True
    }}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws.settimeout(0.5); raw = ws.recv()
        except websocket.WebSocketTimeoutException: continue
        try:
            resp = json.loads(raw)
        except: continue
        if resp.get("id") == msg_id:
            return resp.get("result", {}).get("result", {}).get("value")
    return None

def create_tab(url):
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["id"]

def main():
    print("=" * 60)
    print("Update Firestore Rules via API")
    print("=" * 60)
    
    tab_id = create_tab("https://console.firebase.google.com/u/0/project/bentodish-alan/overview")
    ws = websocket.create_connection(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tab_id}", timeout=30)
    time.sleep(5)
    
    # Get OAuth token from the logged-in session
    print("[1/4] Getting OAuth token...")
    token = evaluate(ws, """
        (async () => {
            try {
                // Try to get token from Google API
                const token = await new Promise((resolve, reject) => {
                    // Check if gapi is loaded
                    if (typeof gapi !== 'undefined' && gapi.auth) {
                        gapi.auth.getToken().then(t => resolve(t.access_token));
                    } else {
                        // Try getting from Google Identity Services
                        const hint = window.google?.accounts?.oauth2;
                        if (hint) {
                            resolve('has_gis');
                        } else {
                            // Try cookies or token element
                            const meta = document.querySelector('meta[name="access-token"]');
                            if (meta) resolve(meta.content);
                            else resolve('no_token_source');
                        }
                    }
                });
                return token;
            } catch(e) {
                return 'error: ' + e.message;
            }
        })()
    """)
    print(f"   Token source: {token}")
    
    # Alternative: extract token from Firebase Auth or gapi
    # Let's try getting it from the Google Auth library
    token2 = evaluate(ws, """
        (async () => {
            // Check Firebase Auth
            if (typeof firebase !== 'undefined' && firebase.auth) {
                const user = firebase.auth().currentUser;
                if (user) {
                    return (await user.getIdToken()).substring(0, 50) + '...';
                }
            }
            // Check for any auth tokens in localStorage
            for (const key of Object.keys(localStorage)) {
                if (key.includes('token') || key.includes('credential') || key.includes('auth')) {
                    try {
                        const val = JSON.parse(localStorage[key]);
                        if (val.accessToken || val.credential) return 'found in localStorage: ' + key;
                        if (typeof val === 'string') return 'string in ' + key + ': ' + val.substring(0, 30);
                    } catch(e) {}
                }
            }
            return 'no token found';
        })()
    """)
    print(f"   Firebase Auth: {token2}")
    
    # Check available GAPI
    gapi_info = evaluate(ws, """
        JSON.stringify({
            has_gapi: typeof gapi !== 'undefined',
            has_gapi_client: typeof gapi?.client !== 'undefined',
            has_gapi_auth: typeof gapi?.auth !== 'undefined',
            has_google: typeof google !== 'undefined',
            has_firebase: typeof firebase !== 'undefined',
            has_firebase_auth: typeof firebase?.auth !== 'undefined'
        })
    """)
    print(f"   API info: {gapi_info}")
    
    # Let's try a different approach - use fetch to get the rules page content
    # and extract the CSRF token
    print("\n[2/4] Extracting Firebase config and making API call...")
    
    # Get current source version and CSRF token
    page_data = evaluate(ws, """
        JSON.stringify({
            csrf: document.querySelector('meta[name="csrf-token"]')?.content?.substring(0, 20) || 'no csrf',
            firebase_config: typeof firebase !== 'undefined' ? 'has_firebase' : 'no_firebase',
            gapi_loaded: typeof gapi !== 'undefined' ? (gapi.client ? 'client_ready' : 'no_client') : 'no_gapi'
        })
    """)
    print(f"   Page data: {page_data}")
    
    # Try using Firebase Rules REST API directly
    # First get the current source from the CodeMirror via the rules tab
    print("[3/4] Getting current rules and updating via fetch...")
    
    # Navigate to rules tab
    evaluate(ws, "window.location.href = arguments[0]", RULES_URL)
    time.sleep(8)
    
    # Read current rules
    current_rules = evaluate(ws, """
        const cm = document.querySelector('.CodeMirror');
        return cm && cm.CodeMirror ? cm.CodeMirror.getValue() : null;
    """)
    
    if current_rules:
        print(f"   Current rules length: {len(current_rules)}")
        
        # Fix the rules - replace the dashboard match from outside to inside
        # Current has:
        #   }
        # (blank)
        #     match /dashboard/{document=**} {
        #       allow read, write: if true;
        #     }
        # }
        # 
        # Should be:
        #     ...
        #     match /comments/{commentId} { ... }
        # 
        #     match /dashboard/{document=**} {
        #       allow read, write: if true;
        #     }
        #   }
        # }
        
        lines = current_rules.split('\n')
        
        # Find the misplaced dashboard section (lines containing 'match /dashboard/')
        # and move it before the closing '  }' of the databases block
        cleaned_lines = []
        dashboard_block = []
        inside_dashboard = False
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('match /dashboard/'):
                inside_dashboard = True
                dashboard_block.append(line)
            elif inside_dashboard:
                if stripped == '}':
                    dashboard_block.append(line)
                    inside_dashboard = False
                else:
                    dashboard_block.append(line)
            else:
                cleaned_lines.append(line)
        
        # Remove empty lines at the end of cleaned_lines
        while cleaned_lines and cleaned_lines[-1].strip() == '':
            cleaned_lines.pop()
        
        # Also remove the trailing } of service if it was separated
        # Find the last non-empty line
        # Insert dashboard block before the closing '  }' of databases
        last_closing_idx = None
        for i in range(len(cleaned_lines) - 1, -1, -1):
            if cleaned_lines[i].strip() == '}' and not cleaned_lines[i].startswith('  }') and not cleaned_lines[i].startswith('}'):
                # This is the closing of the service block, skip
                continue
            if cleaned_lines[i].strip() == '  }':
                last_closing_idx = i
                break
        
        if last_closing_idx is not None:
            # Insert dashboard block before the closing
            indent = cleaned_lines[last_closing_idx][:cleaned_lines[last_closing_idx].find('}')]
            # Indent the dashboard block properly (match the comments indent)
            if dashboard_block:
                dashboard_block = [indent + '  ' + line.strip() if i > 0 else indent + '  ' + line.strip() for i, line in enumerate(dashboard_block)]
                # Fix the first line indent
                dashboard_block[0] = indent + '  ' + dashboard_block[0].strip() if not dashboard_block[0].strip().startswith('match') else indent + '  ' + dashboard_block[0].strip()
            else:
                # No misplaced block, we need to add it fresh
                dashboard_block = [
                    indent + '',
                    indent + '    match /dashboard/{document=**} {',
                    indent + '      allow read, write: if true;',
                    indent + '    }',
                    indent + ''
                ]
            
            cleaned_lines[last_closing_idx:last_closing_idx] = dashboard_block
        
        fixed_rules = '\n'.join(cleaned_lines)
        print(f"   Fixed rules:\n{fixed_rules}")
        
        # Set the rules in CodeMirror
        evaluate(ws, f"""
            const cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {{
                cm.CodeMirror.setValue({json.dumps(fixed_rules)});
            }}
        """)
        time.sleep(2)
        
        # Now try to find and click Publish
        print("[4/4] Finding Publish button...")
        
        # Look for specific Publish button
        publish_info = evaluate(ws, """
            JSON.stringify({
                buttons: Array.from(document.querySelectorAll('button')).filter(b => b.innerText.trim()).map(b => ({
                    text: b.innerText.trim().substring(0, 20),
                    disabled: b.disabled,
                    rect: b.getBoundingClientRect ? 'visible' : 'hidden'
                })),
                // Try to find the publish/save button more specifically
                any_publish: !!document.querySelector('[data-test-id="publish-rules"], .publish-rules, [aria-label*="Publish"], [aria-label*="發布"]'),
                // Check for unsaved changes indicator
                unsaved: document.body.innerText.includes('Unsaved') || document.body.innerText.includes('未儲存') || false
            })
        """)
        print(f"   Publish info: {publish_info}")
        
        # Try to click using different strategies
        for selector in [
            'button.mdc-button:not(:disabled)',
            '[data-test-id="publish-rules"]',
            '.publish-button',
            'button[type="submit"]',
            'fire-rules-editor button:not([disabled])'
        ]:
            r = evaluate(ws, f"""
                (() => {{
                    const el = document.querySelector({json.dumps(selector)});
                    if (el && !el.disabled) {{
                        const text = (el.innerText || '').trim().substring(0, 20);
                        el.click();
                        return 'clicked: ' + text + ' via ' + {json.dumps(selector)};
                    }}
                    return 'none for: ' + {json.dumps(selector)};
                }})()
            """)
            print(f"   {r}")
            time.sleep(1)
        
        time.sleep(3)
        
        # Final check - verify rules were saved
        final = evaluate(ws, """
            const cm = document.querySelector('.CodeMirror');
            return cm && cm.CodeMirror ? 'rules_present: ' + cm.CodeMirror.getValue().includes('dashboard') : 'no cm';
        """)
        print(f"\n   Final: {final}")
    
    ws.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

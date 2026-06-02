# 小紅書 CDP Proxy - Windows 端
# 啟動 CentBrowser + CDP，並監聽本機 CDP API
$ErrorActionPreference = "Continue"

$CENT = "$env:LOCALAPPDATA\CentBrowser\Application\chrome.exe"
$CDP_PORT = 9223
$PROXY_PORT = 5001

Write-Host "=== 小紅書 CDP Proxy ===" -ForegroundColor Cyan
Write-Host ""

# Kill existing CentBrowser with CDP
Write-Host "> 清理舊的 CDP 進程..." -ForegroundColor Yellow
$existing = Get-NetTCPConnection -LocalPort $CDP_PORT -ErrorAction SilentlyContinue
if ($existing) {
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# Start CentBrowser with CDP
Write-Host "> 啟動 CentBrowser (CDP port $CDP_PORT)..." -ForegroundColor Yellow
$args = @("--remote-debugging-port=$CDP_PORT", "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check", "https://www.xiaohongshu.com")
Start-Process -FilePath $CENT -ArgumentList $args

# Wait for CDP to be ready
Write-Host "> 等待 CDP 就緒..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$CDP_PORT/json/version" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "  ✓ CDP ready! CentBrowser: $($resp.Browser)" -ForegroundColor Green
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Host "  ✗ CDP failed to start" -ForegroundColor Red
    exit 1
}

# Start a simple Python HTTP proxy that forwards CDP calls
Write-Host "> 啟動 CDP API Proxy (port $PROXY_PORT)..." -ForegroundColor Yellow
$proxyCode = @"
import json, urllib.request, http.server, sys

CDP = f"http://127.0.0.1:$CDP_PORT"

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            url = CDP + self.path
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            self.send_response(200)
            self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
    
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b'{}'
        try:
            url = CDP + self.path
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=60)
            data = resp.read()
            self.send_response(200)
            self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/json'))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
    
    def log_message(self, format, *args):
        pass

server = http.server.HTTPServer(('0.0.0.0', $PROXY_PORT), ProxyHandler)
print(f"CDP Proxy running on http://0.0.0.0:$PROXY_PORT")
sys.stdout.flush()
server.serve_forever()
"@

# Run the proxy script
python -c $proxyCode

# Keep window open
Read-Host "按 Enter 結束"

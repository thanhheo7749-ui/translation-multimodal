import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page()
    failed_requests = []
    page.on('response', lambda resp: failed_requests.append(f'{resp.status}: {resp.url}') if resp.status >= 400 else None)
    
    page.goto('http://localhost:8004/live')
    page.wait_for_function('state.ready === true')
    print("[1] Page ready. Starting demo video...")
    page.locator('#demo-start').click()
    
    # Wait for 5 seconds of playback
    for sec in range(1, 6):
        time.sleep(1.0)
        info = page.evaluate('''() => {
            return {
                capturing: state.capturing,
                frameCounter: state.vision ? state.vision.frameIdCounter : 0,
                visionStatus: state.vision ? state.vision.status : null,
                slideStatusText: document.getElementById('slide-status') ? document.getElementById('slide-status').textContent : null,
                slideTitleText: document.getElementById('slide-title') ? document.getElementById('slide-title').textContent : null,
                currentTime: document.getElementById('demo-video') ? document.getElementById('demo-video').currentTime : 0
            };
        }''')
        print(f"  Sec {sec}: Time={info['currentTime']:.1f}s | Frames Sent={info['frameCounter']} | Status='{info['slideStatusText']}' | Title='{info['slideTitleText']}'")
        
    print("[2] Failed HTTP requests:", failed_requests)
    browser.close()

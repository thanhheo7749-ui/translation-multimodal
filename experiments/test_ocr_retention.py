import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1366, 'height': 850})
    
    page.goto('http://localhost:8004/live')
    page.wait_for_function('state.ready === true')
    print("[1] Page ready. Starting demo video...")
    page.locator('#demo-start').click()
    
    # Wait until slide is extracted
    for i in range(12):
        time.sleep(0.5)
        st = page.locator('#slide-status').text_content()
        if st == 'Đã trích xuất chữ':
            break
            
    title1 = page.locator('#slide-title').text_content()
    tags1 = [el.text_content() for el in page.locator('.entity-badge').all()]
    print("[2] Extracted Slide:")
    print("    Title:", title1)
    print("    Keywords/Entities:", tags1)
    
    # Assert title is NOT repeated in entities
    assert title1 not in tags1, "Title should not be duplicated in keyword tags!"
    print("    -> PASS: Title is not duplicated in keyword badges.")
    
    # Now uncheck OCR toggle
    print("[3] Toggling off OCR checkbox...")
    page.locator('#slide-enable-checkbox').uncheck()
    time.sleep(0.5)
    
    status2 = page.locator('#slide-status').text_content()
    title2 = page.locator('#slide-title').text_content()
    tags2 = [el.text_content() for el in page.locator('.entity-badge').all()]
    radar_visible = page.locator('#slide-scan-indicator').is_visible()
    
    print("[4] After Turning Off OCR:")
    print("    Status:", status2)
    print("    Title Retained:", title2)
    print("    Keywords Retained:", tags2)
    print("    Radar Scanning Active:", radar_visible)
    
    assert status2 == 'Tạm dừng quét', f"Expected 'Tạm dừng quét', got '{status2}'"
    assert title2 == title1, f"Title should be preserved! Got '{title2}' vs '{title1}'"
    assert tags2 == tags1, "Keywords should be preserved!"
    assert not radar_visible, "Radar indicator must be hidden when OCR is off!"
    print("    -> PASS: All slide data retained and CPU scanning halted!")
    
    page.screenshot(path='experiments/runtime_logs/layout_after_ocr_disabled_retained.png')
    print("[5] Screenshot saved: experiments/runtime_logs/layout_after_ocr_disabled_retained.png")
    
    browser.close()

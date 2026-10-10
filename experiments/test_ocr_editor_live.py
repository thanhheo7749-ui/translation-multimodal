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
    print("[2] Detected Slide Title:", title1)
    
    # Open OCR Modal
    print("[3] Clicking '✏️ Xem & Sửa OCR'...")
    page.locator('#slide-inspect-btn').click()
    time.sleep(0.5)
    
    modal_visible = page.locator('#ocr-modal').is_visible()
    assert modal_visible, "OCR Modal must be visible!"
    print("    -> PASS: OCR Modal opened successfully.")
    
    # Inspect raw list items
    raw_items = [el.text_content() for el in page.locator('.ocr-raw-item').all()]
    print("[4] Raw OCR Items in Modal:", len(raw_items), raw_items[:3])
    assert len(raw_items) > 0, "Raw OCR list should contain detected text blocks!"
    
    # Take screenshot of the modal open
    page.screenshot(path='experiments/runtime_logs/ocr_edit_modal_open.png')
    print("    -> Screenshot of modal saved to experiments/runtime_logs/ocr_edit_modal_open.png")
    
    # Edit Title and Entities
    print("[5] Editing Title and Keywords...")
    page.locator('#ocr-edit-title').fill('40 Years of Personal Computing (Windows XP)')
    page.locator('#ocr-edit-entities').fill('WINDOWS, start, Windows XP, Bill Gates, Keynote')
    
    # Save & Apply
    print("[6] Saving & Applying changes...")
    page.locator('#ocr-modal-save').click()
    time.sleep(1.0)
    
    # Verify modal closed and main UI updated
    modal_closed = not page.locator('#ocr-modal').is_visible()
    new_title = page.locator('#slide-title').text_content()
    new_tags = [el.text_content() for el in page.locator('.entity-badge').all()]
    print("[7] Updated Slide in UI:")
    print("    New Title:", new_title)
    print("    New Tags:", new_tags)
    
    assert modal_closed, "Modal should close after saving!"
    assert new_title == '40 Years of Personal Computing (Windows XP)', f"Title not updated! Got '{new_title}'"
    assert 'Windows XP' in new_tags, "Newly added keyword 'Windows XP' should appear in tags!"
    assert 'Bill Gates' in new_tags, "Newly added keyword 'Bill Gates' should appear in tags!"
    print("    -> PASS: Human-in-the-loop edits applied and reflected in UI!")
    
    # Take screenshot of the updated main layout
    page.screenshot(path='experiments/runtime_logs/layout_after_human_edit.png')
    print("[8] Screenshot saved to experiments/runtime_logs/layout_after_human_edit.png")
    
    browser.close()

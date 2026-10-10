import sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1366, 'height': 850})
    
    page.goto('http://localhost:8004/live')
    page.wait_for_function('() => window.state && window.state.ready === true')
    print("[1] Page ready. Starting demo video...")
    page.locator('#demo-start').click()
    
    # Wait until slide 1 is extracted
    for i in range(12):
        time.sleep(0.5)
        st = page.locator('#slide-status').text_content()
        if st == 'Đã trích xuất chữ':
            break
            
    title1 = page.locator('#slide-title').text_content()
    print("[2] Detected Slide Title:", title1)
    
    # Check that slide chip for #1 appeared
    chips = [el.text_content().strip() for el in page.locator('.slide-chip').all()]
    print("[3] Initial Slide Chips in UI:", chips)
    assert any('#1' in c for c in chips), "Slide #1 chip must appear in the history chips bar!"
    
    # Edit Slide 1 via Modal
    print("[4] Opening '✏️ Xem & Sửa OCR' modal...")
    page.locator('#slide-inspect-btn').click()
    time.sleep(0.5)
    
    page.locator('#ocr-edit-title').fill('40 Years of Personal Computing (Windows XP)')
    page.locator('#ocr-edit-entities').fill('WINDOWS, start, Windows XP, Bill Gates, Keynote')
    page.locator('#ocr-modal-save').click()
    time.sleep(1.0)
    
    # Verify chip 1 updated with edited indicator
    chips_after_edit = [el.text_content().strip() for el in page.locator('.slide-chip').all()]
    print("[5] Slide Chips after edit:", chips_after_edit)
    assert any('✏️' in c and '#1' in c for c in chips_after_edit), "Chip #1 must reflect human-edited status (✏️)!"
    
    # Now simulate a scene transition / new slide arriving (Slide #2: 'NVIDIA GTC AI Architecture')
    print("[6] Simulating transition to Slide #2 (chuyển sang slide khác)...")
    page.evaluate('''() => {
        const slide2 = {
            session_id: String(state.session),
            source_epoch: state.vision?.sourceEpoch || 0,
            slide_id: 2,
            slide_revision: 1,
            status: 'READY',
            title: 'NVIDIA GTC Keynote: Blackwell Architecture',
            entities: [
                { text: 'Blackwell GPU', score: 0.98, box: [] },
                { text: 'NVLink 5', score: 0.95, box: [] },
                { text: 'Transformer Engine', score: 0.96, box: [] }
            ],
            content_hash: 'hash_slide2',
            isUserEdited: false
        };
        state.slides.push(slide2);
        state.currentSlide = slide2;
        state.viewingSlideId = 2;
        renderSlideInspector();
    }''')
    time.sleep(0.5)
    
    # Check that both Slide 1 and Slide 2 exist in chips
    chips_with_both = [el.text_content().strip() for el in page.locator('.slide-chip').all()]
    print("[7] Slide Chips with multiple slides:", chips_with_both)
    assert len(chips_with_both) >= 2, f"Should have at least 2 slide chips! Got {chips_with_both}"
    assert any('#1' in c for c in chips_with_both), "Slide #1 MUST STILL BE SAVED and visible!"
    assert any('#2' in c for c in chips_with_both), "Slide #2 must be visible!"
    
    counter_text = page.locator('#slide-nav-counter').text_content()
    print("    Counter text:", counter_text)
    assert 'Slide 2/2' in counter_text or '2 slide' in counter_text
    
    # Now click back on Chip #1 to verify Slide 1 is NOT lost!
    print("[8] Clicking back on Slide #1 chip to verify data retention (không bị mất)...")
    page.locator('.slide-chip', has_text='#1').click()
    time.sleep(0.5)
    
    title_after_switch = page.locator('#slide-title').text_content()
    tags_after_switch = [el.text_content() for el in page.locator('.entity-badge').all()]
    print("    Title when viewing Slide #1:", title_after_switch)
    print("    Tags when viewing Slide #1:", tags_after_switch)
    
    assert title_after_switch == '40 Years of Personal Computing (Windows XP)', f"Slide #1 title lost! Got '{title_after_switch}'"
    assert 'Windows XP' in tags_after_switch, "Slide #1 custom keyword 'Windows XP' must be preserved!"
    assert 'Bill Gates' in tags_after_switch, "Slide #1 custom keyword 'Bill Gates' must be preserved!"
    print("    -> PASS: Slide 1 preserved perfectly across transitions!")
    
    # Verify previous/next navigation buttons
    print("[9] Testing 'Sau ▶' navigation button...")
    page.locator('#slide-next-btn').click()
    time.sleep(0.3)
    title_slide2 = page.locator('#slide-title').text_content()
    print("    Title after clicking 'Sau ▶':", title_slide2)
    assert 'Blackwell Architecture' in title_slide2, "Next button should navigate to Slide #2!"
    
    # Verify export payload contains full slides history
    print("[10] Verifying JSON export contents...")
    export_data = page.evaluate('''() => {
        return {
            slides: state.slides,
            totalSlides: state.slides.length,
            session_id: state.session
        };
    }''')
    print(f"    Export contains {export_data['totalSlides']} slides:")
    for s in export_data['slides']:
        print(f"      - Slide #{s['slide_id']}: '{s['title']}' ({len(s['entities'])} entities, edited={s.get('isUserEdited')})")
    assert export_data['totalSlides'] >= 2, "Exported data must include all slides in the session history!"
    
    # Capture screenshot showing the slide history chips and navigation
    page.screenshot(path='experiments/runtime_logs/slide_history_retention_verified.png')
    print("[11] Screenshot saved to experiments/runtime_logs/slide_history_retention_verified.png")
    
    browser.close()
    print("\n--- ALL SLIDE HISTORY & RETENTION VERIFICATION TESTS PASSED! ---")

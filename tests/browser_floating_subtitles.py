"""Real Chrome PiP lifecycle, with deterministic ASR/MT state (no API key/capture).
Run manually with host Playwright installed; not a live speech accuracy test.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True,
            args=['--auto-select-tab-capture-source-by-title=Subtitle test audio'])
        context = browser.new_context()
        context.route('**/api/live/warmup', lambda r: r.fulfill(json={'status': 'ok'}))
        context.route('**/test-audio-fixture', lambda r: r.fulfill(content_type='text/html', body='''
            <title>Subtitle test audio</title><button id="tone">Play synthetic tone</button>
            <script>tone.onclick=()=>{const c=new AudioContext();const o=c.createOscillator();
            const g=c.createGain();g.gain.value=.03;o.connect(g);g.connect(c.destination);o.start();};</script>'''))
        context.route('**/api/live/asr', lambda r: r.fulfill(json={
            'status': 'ok', 'words': [], 'text': '', 'asr_latency_ms': 1}))
        fixture = context.new_page()
        fixture.goto('http://localhost:8004/test-audio-fixture')
        fixture.locator('#tone').click()
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto('http://localhost:8004/live')
        page.locator('#pip').wait_for(state='visible')
        page.wait_for_function('state.ready')
        page.locator('#pip').click()
        page.wait_for_function('!!state.pip && !!state.pip.document.getElementById("en")')
        assert page.evaluate('!!window.documentPictureInPicture.window'), 'Must use real PiP, not popup fallback'
        pip_page = next(x for x in context.pages if x not in (page, fixture))
        page.wait_for_function("state.pip.getComputedStyle(state.pip.document.getElementById('vi')).fontSize === '25px'",timeout=5000)
        page.evaluate("() => { state.pip.document.getElementById('pip-share').onclick = () => startCapture('tab'); }")
        pip_page.locator('#pip-share').click()
        page.wait_for_function('state.capturing || document.getElementById("error").textContent', timeout=15000)
        assert page.evaluate('state.capturing'), page.locator('#error').inner_text()
        assert page.evaluate('state.stream.getAudioTracks().length') == 1
        page.evaluate('state.pip.close()')
        page.wait_for_function('state.pip===null')
        page.wait_for_timeout(300)
        assert page.evaluate("state.capturing && state.stream.getAudioTracks()[0].readyState==='live'"), 'PiP close should keep the real capture alive'
        page.bring_to_front()
        page.locator('#pip').click()
        page.wait_for_function('!!state.pip && !!state.pip.document.getElementById("stop")')
        pip_page=next(x for x in context.pages if x not in (page,fixture))
        print('PASS: real tab capture initiated from PiP; source is isolated synthetic tone fixture.')
        pip_page.locator('#stop').click()
        page.wait_for_function('!state.capturing && !state.stopping')
        page.evaluate("""() => {
            state.kind='tab'; state.capturing=true;
            state.rows=[{id:1,status:'ok',en:'English one.',vi:'Vietnamese one.',startSec:0,endSec:1,durationSec:1}];
            render();
        }""")
        assert page.evaluate('state.pip.document.getElementById("en").textContent') == 'English one.'
        other = context.new_page()
        other.goto('about:blank')
        other.bring_to_front()
        assert page.evaluate('!!documentPictureInPicture.window && !state.pip.closed')
        page.evaluate("""() => {
            state.rows.push({id:2,status:'mt',en:'Pending English.',vi:'',startSec:1,endSec:2,durationSec:1});
            render();
        }""")
        assert page.evaluate('state.pip.document.getElementById("vi").textContent') == 'Vietnamese one.'
        page.wait_for_timeout(950)
        page.evaluate("state.rows[1].status='ok';state.rows[1].vi='Vietnamese two.';render()")
        assert page.evaluate('state.pip.document.getElementById("en").textContent') == 'Pending English.'
        assert page.evaluate('state.pip.document.getElementById("vi").textContent') == 'Vietnamese two.'
        destination = ROOT / 'experiments/runtime_logs/floating_subtitles.png'
        destination.parent.mkdir(parents=True, exist_ok=True)
        pip_page.set_viewport_size({'width': 480, 'height': 420})
        pip_page.screenshot(path=str(destination))
        page.evaluate('state.pip.close()')
        page.wait_for_function('state.pip===null')
        assert page.evaluate('state.capturing'), 'Closing PiP must not silently stop capture'
        page.bring_to_front()
        page.locator('#pip').click()
        page.wait_for_function('!!documentPictureInPicture.window')
        assert page.evaluate('state.pip.document.getElementById("vi").textContent') == 'Vietnamese two.'
        assert not errors, errors
        print('PASS: real Chrome PiP, tab switch, matched pairs, close/reopen. Synthetic transcript state; no speech accuracy claim.')
        browser.close()


if __name__ == '__main__':
    main()

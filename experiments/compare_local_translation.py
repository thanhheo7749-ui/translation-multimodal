"""Real NLLB vs the studio Gemini adapter; never saves credentials or mock outputs."""
import argparse
import csv
import importlib.metadata
import json
import random
import math
import os
import getpass
import statistics
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'facebook/nllb-200-distilled-600M'


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=70) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Local studio returns structured errors; retain codes, not raw HTTP bodies.
        try:
            value = json.load(error)
        except (ValueError, OSError):
            value = {}
        code = value.get('error_code', '')
        if not isinstance(code, str) or not code.replace('_', '').isalnum():
            code = 'http_' + str(error.code)
        raise ProviderFailure(code) from None


class ProviderFailure(RuntimeError):
    pass


import sys
sys.path.insert(0, str(ROOT))
from backend.translation.nllb_engine import NLLB


def summarize(rows):
    result = {}
    for provider in sorted({r['provider'] for r in rows}):
        selected = [r for r in rows if r['provider'] == provider]
        latencies = [r['latency_ms'] for r in selected if r['status'] == 'ok']
        result[provider] = {'attempts': len(selected), 'successes': len(latencies),
            'failures': len(selected) - len(latencies),
            'median_ms': round(statistics.median(latencies), 1) if latencies else None,
            'p95_ms': sorted(latencies)[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
            'max_ms': max(latencies) if latencies else None}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--providers', choices=['both', 'gemini', 'local'], default='both')
    parser.add_argument('--server', default='http://127.0.0.1:8003')
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--beam-size', type=int, choices=[1, 4], default=4)
    parser.add_argument('--interval', type=float, default=1.0, help='Pause between requests, seconds')
    parser.add_argument('--gemini-direct', action='store_true', help='Use the same Gemini adapter in this process, without a separate server')
    parser.add_argument('--prompt-key', action='store_true', help='Read API key with hidden terminal input for this process only')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10: parser.error('repeats must be 1..10')
    if not 0 <= args.interval <= 60: parser.error('interval must be 0..60')
    if args.prompt_key and not args.gemini_direct: parser.error('--prompt-key requires --gemini-direct')
    fixture = json.loads((ROOT / 'experiments/local_comparison_cases.json').read_text(encoding='utf-8'))
    cases = fixture['cases']
    out = ROOT / 'experiments/local_comparison' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out.mkdir(parents=True)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'text translation only; not ASR or live subtitle latency',
        'requested_providers': args.providers,
        'source': fixture['source'], 'source_videos': 1, 'unique_inputs': len(cases), 'technical_repeats': args.repeats,
        'request_interval_sec': args.interval,
        'quality_score': 'NOT_SCORED: no verified reference or independent human ratings', 'models': {}, 'warmups': [], 'rows': []}
    providers = {}
    if args.providers in ('both', 'gemini'):
        try:
            direct_service = None
            if args.gemini_direct:
                from backend.translation.live_service import LiveTranslationService
                from backend.translation.contracts import TranslationRequest
                if args.prompt_key and not os.getenv('GEMINI_API_KEY'):
                    os.environ['GEMINI_API_KEY'] = getpass.getpass('Gemini API key (hidden): ').strip()
                direct_service = LiveTranslationService()
                direct_service.provider = 'gemini'
                direct_service.model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
                info = direct_service.info()
            else:
                info = request_json(args.server + '/api/translation-status')
            if info.get('provider') != 'gemini' or not info.get('configured'):
                raise RuntimeError('Server must be configured with Gemini')
            report['models']['gemini'] = {'model': info.get('model'), 'transport':
                'same Gemini adapter, direct HTTPS' if direct_service else 'HTTP to configured Gemini server'}
            def gemini(text):
                started = time.perf_counter()
                if direct_service:
                    value = direct_service.translate(TranslationRequest('benchmark', text)).to_dict()
                else:
                    value = request_json(args.server + '/api/translate-test', {'text': text, 'previous_context': '', 'mode': 'stream'})
                if value.get('status') != 'ok': raise ProviderFailure(value.get('error_code', 'translation_failed'))
                return {'translation': value['translated_text'], 'latency_ms': round((time.perf_counter()-started)*1000, 1),
                    'provider_ms': value.get('latency_ms'), 'model': value.get('model')}
            providers['gemini'] = gemini
        except Exception as e:
            report['models']['gemini'] = {'status': 'unavailable', 'error_type': type(e).__name__}
            print('Gemini unavailable:', type(e).__name__, flush=True)
    if args.providers in ('both', 'local'):
        try:
            print('Loading real NLLB weights. First download can take several minutes.', flush=True)
            local = NLLB(args.download, args.device, beam_size=args.beam_size)
            report['models']['local'] = local.metadata
            providers['local'] = local.translate
        except Exception as e:
            report['models']['local'] = {'status': 'unavailable', 'error_type': type(e).__name__}
            print('Local model unavailable:', str(e)[:600], flush=True)
    warmup_text = 'Hello, and welcome to this presentation.'
    for provider, translate in providers.items():
        try:
            value = translate(warmup_text)
            report['warmups'].append({'provider': provider, 'status': 'ok', **value})
        except Exception as e:
            report['warmups'].append({'provider': provider, 'status': 'error', 'error_type': type(e).__name__})
    rng = random.Random(42)
    for repeat in range(args.repeats):
        ordered_cases = cases.copy(); rng.shuffle(ordered_cases)
        for case in ordered_cases:
            order = list(providers); rng.shuffle(order)
            for provider in order:
                row = {'provider': provider, 'case_id': case['id'], 'repeat': repeat, 'source': case['text']}
                attempt_started = time.perf_counter()
                try: row.update(status='ok', **providers[provider](case['text']))
                except Exception as e:
                    row.update(status='error', error_type=type(e).__name__,
                        elapsed_ms=round((time.perf_counter()-attempt_started)*1000, 1))
                    if isinstance(e, ProviderFailure): row['error_code'] = str(e)
                report['rows'].append(row)
                (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(provider, case['id'], repeat + 1, row['status'], row.get('latency_ms'), flush=True)
                time.sleep(max(0, args.interval))
    report['summary'] = summarize(report['rows'])
    if 'local' in providers and args.device == 'cuda':
        report['models']['local']['peak_allocated_mib'] = round(local.torch.cuda.max_memory_allocated()/2**20, 1)
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Local vs Gemini — phép thử dịch văn bản', '', report['scope'],
        '', '| Provider | Thành công / thử | Trung vị ms | Max ms |', '|---|---:|---:|---:|']
    for provider, s in report['summary'].items():
        lines.append(f"| {provider} | {s['successes']}/{s['attempts']} | {s['median_ms']} | {s['max_ms']} |")
    missing = [p for p in ('local', 'gemini') if p not in providers]
    lines += ['', 'Chưa có kết quả: ' + ', '.join(missing) if missing else 'Hai provider đã được thử.',
        '', 'Một video, sáu đầu vào ASR chưa được duyệt; số lần lặp không phải số mẫu độc lập.',
        'Không có điểm chất lượng chuẩn hoặc kết luận model nào tốt hơn. Latency local gồm tokenizer/generate/decode; Gemini gồm HTTP localhost + API.',
        'Warmup và tải/nạp model được ghi riêng trong results.json; không tính vào bảng trên.']
    (out / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    with (out / 'translations.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['case_id','source','provider','repeat','status','translation','latency_ms','human_meaning_errors','human_term_errors'], extrasaction='ignore')
        writer.writeheader();writer.writerows(report['rows'])
    print('REPORT:', out, flush=True)
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    requested = {'local','gemini'} if args.providers == 'both' else {args.providers}
    return 0 if requested <= providers.keys() and all(r['status']=='ok' for r in report['rows']) else 2


if __name__ == '__main__':
    raise SystemExit(main())

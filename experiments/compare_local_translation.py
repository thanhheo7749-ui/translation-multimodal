"""Real NLLB vs running Gemini server; no mock outputs and no API key handling."""
import argparse
import csv
import importlib.metadata
import json
import random
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'facebook/nllb-200-distilled-600M'


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=70) as response:
        return json.load(response)


class NLLB:
    def __init__(self, download=False, device='cuda'):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from huggingface_hub import snapshot_download
        self.torch = torch
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; GPU run not replaced silently by CPU. Use --device cpu to measure CPU explicitly.')
        self.device = device
        torch.set_num_threads(4)
        started = time.perf_counter()
        folder = snapshot_download(MODEL, cache_dir=str(ROOT / 'models' / 'hf-cache'), local_files_only=not download,
            allow_patterns=['config.json','generation_config.json','pytorch_model.bin','tokenizer.json',
                'tokenizer_config.json','special_tokens_map.json','sentencepiece.bpe.model'])
        download_ms = round((time.perf_counter()-started)*1000, 1)
        started = time.perf_counter()
        options = dict(local_files_only=True, trust_remote_code=False)
        self.tokenizer = AutoTokenizer.from_pretrained(folder, src_lang='eng_Latn', **options)
        # Official repository publishes pytorch_model.bin. Recent PyTorch uses
        # restricted weights-only loading; do not execute repository code.
        self.model = AutoModelForSeq2SeqLM.from_pretrained(folder, use_safetensors=False, weights_only=True,
            torch_dtype=torch.float16 if device == 'cuda' else torch.float32, **options).to(device).eval()
        self.sync()
        self.load_ms = round((time.perf_counter() - started) * 1000, 1)
        self.target_id = self.tokenizer.convert_tokens_to_ids('vie_Latn')
        if self.target_id == self.tokenizer.unk_token_id:
            raise RuntimeError('Vietnamese language token not found')
        self.metadata = {'model': MODEL, 'revision': Path(folder).name,
            'device': device, 'resolve_or_download_ms': download_ms, 'model_load_ms': self.load_ms,
            'dtype': str(self.model.dtype), 'beam_size': 4,
            'packages': {p: importlib.metadata.version(p) for p in ('torch', 'transformers', 'tokenizers', 'sentencepiece')},
            'gpu': torch.cuda.get_device_name(0) if device == 'cuda' else None}

    def sync(self):
        if self.device == 'cuda': self.torch.cuda.synchronize()

    def translate(self, text):
        self.sync()
        started = time.perf_counter()
        inputs = self.tokenizer(text, return_tensors='pt').to(self.device)
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, forced_bos_token_id=self.target_id,
                max_new_tokens=192, num_beams=4, do_sample=False)
        self.sync()
        result = self.tokenizer.batch_decode(output, skip_special_tokens=True)[0].strip()
        elapsed = (time.perf_counter() - started) * 1000
        if not result: raise RuntimeError('Empty local translation')
        if int(output[0, -1]) != self.model.config.eos_token_id:
            raise RuntimeError('Output hit token limit without EOS; not counted as success')
        return {'translation': result, 'latency_ms': round(elapsed, 1)}


def summarize(rows):
    result = {}
    for provider in sorted({r['provider'] for r in rows}):
        selected = [r for r in rows if r['provider'] == provider]
        latencies = [r['latency_ms'] for r in selected if r['status'] == 'ok']
        result[provider] = {'attempts': len(selected), 'successes': len(latencies),
            'failures': len(selected) - len(latencies),
            'median_ms': round(statistics.median(latencies), 1) if latencies else None,
            'max_ms': max(latencies) if latencies else None}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--providers', choices=['both', 'gemini', 'local'], default='both')
    parser.add_argument('--server', default='http://127.0.0.1:8003')
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10: parser.error('repeats must be 1..10')
    fixture = json.loads((ROOT / 'experiments/local_comparison_cases.json').read_text(encoding='utf-8'))
    cases = fixture['cases']
    out = ROOT / 'experiments/local_comparison' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out.mkdir(parents=True)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'text translation only; not ASR or live subtitle latency',
        'source': fixture['source'], 'source_videos': 1, 'unique_inputs': len(cases), 'technical_repeats': args.repeats,
        'quality_score': 'NOT_SCORED: no verified reference or independent human ratings', 'models': {}, 'warmups': [], 'rows': []}
    providers = {}
    if args.providers in ('both', 'gemini'):
        try:
            info = request_json(args.server + '/api/translation-status')
            if info.get('provider') != 'gemini' or not info.get('configured'):
                raise RuntimeError('Server must be configured with Gemini')
            report['models']['gemini'] = {'model': info.get('model'), 'transport': 'localhost HTTP to configured Gemini server'}
            def gemini(text):
                started = time.perf_counter()
                value = request_json(args.server + '/api/translate-test', {'text': text, 'previous_context': '', 'mode': 'stream'})
                if value.get('status') != 'ok': raise RuntimeError(value.get('error_code', 'translation_failed'))
                return {'translation': value['translated_text'], 'latency_ms': round((time.perf_counter()-started)*1000, 1),
                    'provider_ms': value.get('latency_ms'), 'model': value.get('model')}
            providers['gemini'] = gemini
        except Exception as e:
            report['models']['gemini'] = {'status': 'unavailable', 'error_type': type(e).__name__}
            print('Gemini unavailable:', type(e).__name__, flush=True)
    if args.providers in ('both', 'local'):
        try:
            print('Loading real NLLB weights. First download can take several minutes.', flush=True)
            local = NLLB(args.download, args.device)
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
                try: row.update(status='ok', **providers[provider](case['text']))
                except Exception as e: row.update(status='error', error_type=type(e).__name__)
                report['rows'].append(row)
                (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(provider, case['id'], repeat + 1, row['status'], row.get('latency_ms'), flush=True)
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

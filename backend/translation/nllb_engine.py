"""Shared, real English-to-Vietnamese NLLB engine for serving and evaluation."""
import importlib.metadata
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = 'facebook/nllb-200-distilled-600M'
MODEL_REVISION = 'f8d333a098d19b4fd9a8b18f94170487ad3f821d'

class NLLB:
    def __init__(self, download=False, device='cuda', beam_size=4):
        self.beam_size = beam_size
        self._lock = threading.Lock()
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from huggingface_hub import snapshot_download
        self.torch = torch
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; GPU run not replaced silently by CPU. Use --device cpu to measure CPU explicitly.')
        self.device = device
        torch.set_num_threads(4)
        started = time.perf_counter()
        folder = snapshot_download(MODEL, revision=MODEL_REVISION, cache_dir=os.getenv('LOCAL_MODEL_CACHE', str(ROOT / 'models' / 'hf-cache')), local_files_only=not download,
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
            'dtype': str(self.model.dtype), 'beam_size': self.beam_size,
            'packages': {p: importlib.metadata.version(p) for p in ('torch', 'transformers', 'tokenizers', 'sentencepiece')},
            'gpu': torch.cuda.get_device_name(0) if device == 'cuda' else None}

    def sync(self):
        if self.device == 'cuda': self.torch.cuda.synchronize()

    def translate(self, text):
        with self._lock:
            return self._translate(text)

    def _translate(self, text):
        self.sync()
        started = time.perf_counter()
        inputs = self.tokenizer(text, return_tensors='pt').to(self.device)
        if inputs['input_ids'].shape[-1] > 512:
            raise ValueError('Local translation input exceeds 512 tokens; split the speech first')
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, forced_bos_token_id=self.target_id,
                max_new_tokens=192, num_beams=self.beam_size, do_sample=False)
        self.sync()
        result = self.tokenizer.batch_decode(output, skip_special_tokens=True)[0].strip()
        elapsed = (time.perf_counter() - started) * 1000
        if not result: raise RuntimeError('Empty local translation')
        if int(output[0, -1]) != self.model.config.eos_token_id:
            raise RuntimeError('Output hit token limit without EOS; not counted as success')
        return {'translation': result, 'latency_ms': round(elapsed, 1)}



_engine = None
_engine_lock = threading.Lock()

def get_local_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = NLLB(download=os.getenv('ALLOW_MODEL_DOWNLOAD', '0') == '1',
                device=os.getenv('LOCAL_DEVICE', 'cuda'),
                beam_size=int(os.getenv('LOCAL_BEAM_SIZE', '4')))
    return _engine

import json
import threading
import urllib.error
import urllib.request
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from backend.asr.whisper_engine import LiveWhisperEngine
from backend.server import StudioHandler
from backend.translation.live_service import TranslationOutcome


class QuietHandler(StudioHandler):
    def log_message(self,*args): pass


class PCMTests(unittest.TestCase):
    def engine(self):
        engine=LiveWhisperEngine.__new__(LiveWhisperEngine)
        engine._inference_lock=threading.Lock();engine.model=Mock()
        engine.model.transcribe.return_value=(iter([SimpleNamespace(text=' Hello there. ',start=0,end=1)]),None)
        return engine

    def test_pcm_normalization_and_only_received_input(self):
        engine=self.engine();pcm=np.full(16000,16384,dtype='<i2').tobytes()
        result=engine.transcribe_pcm(pcm)
        audio=engine.model.transcribe.call_args.args[0]
        self.assertEqual(len(audio),16000);self.assertTrue(np.all(audio==.5))
        self.assertEqual(result['text'],'Hello there.');self.assertEqual(result['audio_duration_sec'],1)
        self.assertTrue(engine.model.transcribe.call_args.kwargs['vad_filter'])
        self.assertFalse(engine.model.transcribe.call_args.kwargs['condition_on_previous_text'])

    def test_invalid_pcm_does_not_invoke_model(self):
        for pcm in (b'',b'x'*3201,b'x'*384002):
            engine=self.engine()
            with self.assertRaises(ValueError):engine.transcribe_pcm(pcm)
            engine.model.transcribe.assert_not_called()


class LiveAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)
    def post(self,path,body=b'',headers=None):
        request=urllib.request.Request(self.base+path,data=body,headers=headers or {},method='POST')
        try:
            with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:return error.code,json.loads(error.read())

    def test_live_page_and_worklet_are_served(self):
        for path,marker in [('/live',b'Share tab audio'),('/pcm-worklet.js',b"registerProcessor('pcm16k'"),('/live-core.js',b'Segmenter')]:
            with urllib.request.urlopen(self.base+path,timeout=3) as response:
                self.assertEqual(response.status,200);self.assertIn(marker,response.read())

    def test_invalid_audio_is_rejected_before_loading_model(self):
        with patch('backend.server.LiveWhisperEngine.get_instance') as getter:
            status,_=self.post('/api/live/asr',b'xx',{'X-Sample-Rate':'16000'})
            getter.assert_not_called()
        self.assertEqual(status,400)

    def test_nvidia_video_fetch_only_serves_bytes_without_inference(self):
        from backend.server import DEFAULT_VIDEO
        request=urllib.request.Request(self.base+'/api/nvidia-video',headers={'Range':'bytes=0-127'})
        with patch('backend.server.ACTIVE_VIDEO','unrelated-upload.mp4'),patch('backend.server.LiveWhisperEngine.get_instance') as asr,patch('backend.server.LiveTranslationService') as translator,patch('backend.server.LivePipelineManager.get_instance') as batch:
            with urllib.request.urlopen(request,timeout=3) as response:
                self.assertEqual(response.status,206)
                payload=response.read()
            with open(DEFAULT_VIDEO,'rb') as video:
                self.assertEqual(payload,video.read(128))
            asr.assert_not_called();translator.assert_not_called();batch.assert_not_called()

    def test_pcm_chunk_reaches_engine_intact(self):
        engine=Mock();engine.transcribe_pcm.return_value={'text':'Hello','asr_latency_ms':20,'audio_duration_sec':1,'segments':[]}
        pcm=np.full(16000,123,dtype='<i2').tobytes()
        with patch('backend.server.LiveWhisperEngine.get_instance',return_value=engine):
            status,result=self.post('/api/live/asr',pcm,{'X-Sample-Rate':'16000','Content-Type':'application/octet-stream'})
        self.assertEqual(status,200);self.assertEqual(result['text'],'Hello')
        engine.transcribe_pcm.assert_called_once_with(pcm)

    def test_foreign_origin_cannot_spend_local_provider_key(self):
        with patch('backend.server.LiveTranslationService') as service:
            status,_=self.post('/api/translate-test',b'{"text":"Hello"}',{'Origin':'https://unrelated.example','Content-Type':'application/json'})
        self.assertEqual(status,403);service.assert_not_called()

    def test_translation_receives_previous_source_context(self):
        service=Mock();service.model='test-model';service.translate.return_value=TranslationOutcome('ok','gemini',translated_text='Xin chào')
        with patch('backend.server.LiveTranslationService',return_value=service),patch('backend.server.save_attempt'):
            status,_=self.post('/api/translate-test',json.dumps({'text':'Hello','previous_context':'We discuss attention.','model':'test-model','mode':'stream'}).encode(),{'Content-Type':'application/json'})
        self.assertEqual(status,200)
        self.assertEqual(service.translate.call_args.args[0].previous_context,'We discuss attention.')

    def test_status_can_respond_while_asr_is_busy(self):
        entered=threading.Event();release=threading.Event()
        def slow(_):
            entered.set();release.wait(timeout=4)
            return {'text':'Hello','asr_latency_ms':1}
        engine=Mock();engine.transcribe_pcm.side_effect=slow
        with patch('backend.server.LiveWhisperEngine.get_instance',return_value=engine):
            worker=threading.Thread(target=lambda:self.post('/api/live/asr',b'\x00'*3200,{'X-Sample-Rate':'16000'}))
            worker.start();self.assertTrue(entered.wait(timeout=2))
            try:
                with urllib.request.urlopen(self.base+'/api/translation-status',timeout=2) as response:
                    self.assertTrue(json.loads(response.read())['live_audio_enabled'])
            finally:release.set();worker.join(timeout=3)


if __name__=='__main__':unittest.main()

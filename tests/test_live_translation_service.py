import io
import json
import os
import socket
import ssl
import tempfile
from pathlib import Path
import urllib.error
import unittest
from unittest.mock import Mock, patch

from backend.translation.contracts import TranslationRequest
from backend.translation.live_service import LiveTranslationService, TranslationOutcome
from backend.live_pipeline import LivePipelineManager
from backend.translation.network_support import classify_network_error, verified_ssl_context
from backend.translation.diagnostic_log import save_attempt


def response(data):
    value = Mock()
    value.__enter__ = Mock(return_value=io.BytesIO(json.dumps(data).encode()))
    value.__exit__ = Mock(return_value=False)
    return value


def stream_response(chunks):
    value=Mock()
    content=b''.join(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode('utf-8') for chunk in chunks)
    value.__enter__=Mock(return_value=io.BytesIO(content))
    value.__exit__=Mock(return_value=False)
    return value


class LiveTranslationTests(unittest.TestCase):
    def test_network_denial_does_not_echo_source(self):
        reason=OSError('denied'); reason.winerror=10013
        with patch.dict(os.environ, {'TRANSLATION_PROVIDER':'google-demo'}), patch('urllib.request.urlopen',side_effect=urllib.error.URLError(reason)):
            result=LiveTranslationService().translate(TranslationRequest('r','Your companies started here.'))
        self.assertEqual(result.status,'error'); self.assertEqual(result.error_code,'network_blocked')
        self.assertEqual(result.translated_text,'')

    def test_real_response_is_parsed(self):
        with patch.dict(os.environ, {'TRANSLATION_PROVIDER':'google-demo'}), patch('urllib.request.urlopen',return_value=response([[['Các công ty của bạn khởi đầu ở đây.']]])):
            result=LiveTranslationService().translate(TranslationRequest('r','Your companies started here.'))
        self.assertEqual(result.status,'ok'); self.assertIn('Các công ty',result.translated_text)
        self.assertFalse(result.context_supported)

    def test_missing_key_does_not_send_request(self):
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':''}), patch('urllib.request.urlopen') as opener:
            result=LiveTranslationService().translate(TranslationRequest('r','Hello'))
            opener.assert_not_called()
        self.assertEqual(result.error_code,'missing_api_key')

    def test_gemini_receives_context_and_header_key(self):
        data={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Bản dịch'}]}}]}
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_MODEL':'test-model'}), patch('urllib.request.urlopen',return_value=response(data)) as opener:
            result=LiveTranslationService().translate(TranslationRequest('r','This slide shows the result.',slide_title='Attention',relevant_entities=['Qwen']))
        request=opener.call_args.args[0]
        self.assertIn('Attention',request.data.decode()); self.assertIn('Qwen',request.data.decode())
        self.assertNotIn('fixture-secret',request.full_url)
        self.assertNotIn('fixture-secret',json.dumps(result.to_dict()))
        self.assertEqual(result.status,'ok')

    def test_http_error_keeps_credential_out_of_output(self):
        error=urllib.error.HTTPError('https://test/?key=fixture-secret',403,'fixture-secret',{},None)
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'google-demo'}),patch('urllib.request.urlopen',side_effect=error):
            result=LiveTranslationService().translate(TranslationRequest('r','Hello'))
        self.assertEqual(result.error_code,'http_403'); self.assertNotIn('fixture-secret',json.dumps(result.to_dict()))

    def test_unchanged_output_requires_review(self):
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'google-demo'}),patch('urllib.request.urlopen',return_value=response([[['Hello']]])):
            result=LiveTranslationService().translate(TranslationRequest('r','Hello'))
        self.assertEqual(result.error_code,'unchanged_output'); self.assertEqual(result.translated_text,'')

    def test_pipeline_marks_failure_and_does_not_claim_revision(self):
        manager=LivePipelineManager.__new__(LivePipelineManager)
        manager.asr_engine=Mock()
        manager.asr_engine.transcribe_slice.return_value=[{'start':0,'end':2,'text':'This is a test.','asr_latency_ms':100}, {'start':3,'end':4,'text':'And it works.','asr_latency_ms':100}]
        service=Mock(); service.translate.return_value=TranslationOutcome('error','google-demo',error_code='network_blocked',message='Cannot translate')
        with patch('backend.live_pipeline.LiveTranslationService',return_value=service):
            rows=manager.process_video_on_the_fly('fixture.mp4',35)
        self.assertEqual(service.translate.call_count,2)
        for row in rows:
            self.assertEqual(row['status'],'translation_error'); self.assertEqual(row['vi_adaptive'],'')
            self.assertFalse(row['is_revision']); self.assertEqual(row['stream_chunks'],[])
        self.assertTrue(rows[1]['revision_requested'])

    def test_invalid_provider_does_not_fall_back_to_mock(self):
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'bad-provider'}),patch('urllib.request.urlopen') as opener:
            result=LiveTranslationService().translate(TranslationRequest('r','Hello'))
            opener.assert_not_called()
        self.assertEqual(result.error_code,'unsupported_provider')

    def test_selected_stable_model_uses_low_thinking(self):
        data={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Xin chào'}]}}]}
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_MODEL':'gemini-3.8-flash'}),patch('urllib.request.urlopen',return_value=response(data)) as opener:
            LiveTranslationService().translate(TranslationRequest('r','Hello'))
        payload=json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload['generationConfig']['thinkingConfig']['thinkingLevel'],'low')

    def test_transport_errors_have_distinct_safe_codes(self):
        cases=[(TimeoutError('fixture-secret'),'network_timeout'),
            (socket.gaierror(-2,'fixture-secret'),'dns_error'),
            (ssl.SSLCertVerificationError(1,'fixture-secret'),'tls_certificate_error'),
            (ConnectionResetError('fixture-secret'),'connection_reset')]
        for reason,expected in cases:
            with self.subTest(expected=expected):
                code,message,details=classify_network_error(urllib.error.URLError(reason))
                self.assertEqual(code,expected)
                self.assertNotIn('fixture-secret',json.dumps([message,details]))

    def test_extra_ca_does_not_disable_tls_verification(self):
        context=verified_ssl_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)

    def test_model_access_checks_metadata_without_generating(self):
        data={'name':'models/test-model','supportedGenerationMethods':['generateContent']}
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_MODEL':'test-model'}),patch('urllib.request.urlopen',return_value=response(data)) as opener:
            outcome=LiveTranslationService().check_access()
        request=opener.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertTrue(request.full_url.endswith('/models/test-model'))
        self.assertEqual(outcome.status,'ok'); self.assertEqual(outcome.phase,'model_access')
        self.assertEqual(outcome.translated_text,'')

    def test_model_check_missing_key_sends_nothing(self):
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':''}),patch('urllib.request.urlopen') as opener:
            outcome=LiveTranslationService().check_access()
        opener.assert_not_called(); self.assertEqual(outcome.error_code,'missing_api_key')

    def test_invalid_key_reason_is_reported_without_remote_body(self):
        payload={'error':{'status':'INVALID_ARGUMENT','message':'fixture-secret',
            'details':[{'reason':'API_KEY_INVALID'}]}}
        error=urllib.error.HTTPError('https://test/?key=fixture-secret',400,'fixture-secret',{},io.BytesIO(json.dumps(payload).encode()))
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret'}),patch('urllib.request.urlopen',side_effect=error):
            outcome=LiveTranslationService().check_access()
        self.assertEqual(outcome.error_code,'invalid_api_key')
        self.assertEqual(outcome.diagnostic['api_reason'],'API_KEY_INVALID')
        self.assertNotIn('fixture-secret',json.dumps(outcome.to_dict()))

    def test_quota_and_model_failure_are_not_network_errors(self):
        for status,code in [(429,'quota_exceeded'),(404,'model_unavailable')]:
            with self.subTest(status=status):
                error=urllib.error.HTTPError('https://test',status,'error',{},io.BytesIO(b'{}'))
                with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret'}),patch('urllib.request.urlopen',side_effect=error):
                    outcome=LiveTranslationService().check_access()
                self.assertEqual(outcome.error_code,code)

    def test_diagnostic_log_omits_translation_and_message(self):
        outcome=TranslationOutcome('ok','gemini',translated_text='private translation',message='fixture-secret',phase='model_access')
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'attempts.jsonl'
            save_attempt(outcome,'test-model',file)
            content=file.read_text()
        self.assertNotIn('private translation',content); self.assertNotIn('fixture-secret',content)
        self.assertEqual(json.loads(content)['phase'],'model_access')

    def test_metadata_without_generation_is_not_access_success(self):
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret'}),patch('urllib.request.urlopen',return_value=response({'supportedGenerationMethods':['embedContent']})):
            outcome=LiveTranslationService().check_access()
        self.assertEqual(outcome.status,'error'); self.assertEqual(outcome.error_code,'unsupported_generation')

    def test_stream_joins_text_and_excludes_thoughts(self):
        chunks=[{'candidates':[{'content':{'parts':[{'text':'private reasoning','thought':True},{'text':'Các công ty '}]}}]},
            {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'của bạn bắt đầu ở đây.'}]}}]}]
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_MODEL':'gemini-3.5-flash-lite','GEMINI_GENERATION_MODE':'stream'}),patch('urllib.request.urlopen',return_value=stream_response(chunks)) as opener:
            outcome=LiveTranslationService().translate(TranslationRequest('r','Your companies started here.'))
        self.assertEqual(outcome.status,'ok')
        self.assertEqual(outcome.translated_text,'Các công ty của bạn bắt đầu ở đây.')
        self.assertIn('first_text_ms',outcome.diagnostic)
        request=opener.call_args.args[0]
        self.assertTrue(request.full_url.endswith(':streamGenerateContent?alt=sse'))
        self.assertNotIn('fixture-secret',request.full_url)
        self.assertEqual(json.loads(request.data)['generationConfig']['thinkingConfig']['thinkingLevel'],'minimal')

    def test_stream_truncated_output_is_not_committed(self):
        chunk={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'Một phần'}]}}]}
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_GENERATION_MODE':'stream'}),patch('urllib.request.urlopen',return_value=stream_response([chunk])):
            outcome=LiveTranslationService().translate(TranslationRequest('r','Some speech'))
        self.assertEqual(outcome.error_code,'incomplete_generation')
        self.assertEqual(outcome.translated_text,'')

    def test_header_timeout_records_stage(self):
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret'}),patch('urllib.request.urlopen',side_effect=TimeoutError()):
            outcome=LiveTranslationService().translate(TranslationRequest('r','Hello'))
        self.assertEqual(outcome.error_code,'network_timeout')
        self.assertEqual(outcome.diagnostic['stage'],'connect_or_response_headers')
        self.assertNotIn('response_headers_ms',outcome.diagnostic)

    def test_body_timeout_keeps_timing_but_no_partial_translation(self):
        class BrokenStream:
            def __iter__(self):
                yield b'data: {"candidates":[{"content":{"parts":[{"text":"Partial"}]}}]}\n'
                yield b'\n'
                raise TimeoutError()
        transport=Mock(); transport.__enter__=Mock(return_value=BrokenStream()); transport.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_GENERATION_MODE':'stream'}),patch('urllib.request.urlopen',return_value=transport):
            outcome=LiveTranslationService().translate(TranslationRequest('r','Hello'))
        self.assertEqual(outcome.diagnostic['stage'],'response_body')
        self.assertIn('response_headers_ms',outcome.diagnostic); self.assertIn('first_text_ms',outcome.diagnostic)
        self.assertEqual(outcome.translated_text,'')

    def test_json_comparison_uses_same_prompt_and_thinking(self):
        payloads=[]
        data={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Xin chào'}]}}]}
        for mode in ('stream','json'):
            with patch.dict(os.environ,{'TRANSLATION_PROVIDER':'gemini','GEMINI_API_KEY':'fixture-secret','GEMINI_MODEL':'gemini-3.5-flash-lite','GEMINI_GENERATION_MODE':mode}),patch('urllib.request.urlopen',return_value=response(data)) as opener:
                outcome=LiveTranslationService().translate(TranslationRequest('r','Hello'))
            self.assertEqual(outcome.status,'ok')
            payloads.append(json.loads(opener.call_args.args[0].data))
        self.assertEqual(payloads[0],payloads[1])


if __name__=='__main__': unittest.main()

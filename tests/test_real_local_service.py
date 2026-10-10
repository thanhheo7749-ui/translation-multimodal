import os
import unittest
from unittest.mock import Mock, patch
from backend.translation.contracts import TranslationRequest
from backend.translation.live_service import LiveTranslationService


class LocalServiceTests(unittest.TestCase):
    def test_local_output_and_no_false_visual_context_claim(self):
        engine = Mock()
        engine.translate.return_value = {'translation': 'Xin chào.', 'latency_ms': 123}
        with patch.dict(os.environ, {'TRANSLATION_PROVIDER': 'local'}), patch(
                'backend.translation.live_service.get_local_engine', return_value=engine):
            service = LiveTranslationService()
            result = service.translate(TranslationRequest('x', 'Hello.', slide_title='Context'))
        self.assertTrue(service.info()['configured'])
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.translated_text, 'Xin chào.')
        self.assertFalse(result.context_supported)
        engine.translate.assert_called_once_with('Hello.')

    def test_missing_weights_returns_error_without_source_echo(self):
        with patch.dict(os.environ, {'TRANSLATION_PROVIDER': 'local'}), patch(
                'backend.translation.live_service.get_local_engine', side_effect=OSError('secret details')):
            result = LiveTranslationService().translate(TranslationRequest('x', 'Hello.'))
        self.assertEqual(result.error_code, 'local_model_error')
        self.assertEqual(result.translated_text, '')
        self.assertNotIn('secret details', str(result.to_dict()))

    def test_identical_source_output_is_not_success(self):
        engine = Mock()
        engine.translate.return_value = {'translation': 'Hello.'}
        with patch.dict(os.environ, {'TRANSLATION_PROVIDER': 'local'}), patch(
                'backend.translation.live_service.get_local_engine', return_value=engine):
            result = LiveTranslationService().translate(TranslationRequest('x', 'Hello.'))
        self.assertEqual(result.error_code, 'unchanged_output')

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import compare_local_translation as benchmark


class ComparisonTests(unittest.TestCase):
    def test_failed_requests_remain_in_denominator(self):
        rows = [dict(provider='local', status='ok', latency_ms=100),
                dict(provider='local', status='error'),
                dict(provider='gemini', status='error')]
        result = benchmark.summarize(rows)
        self.assertEqual(result['local']['attempts'], 2)
        self.assertEqual(result['local']['successes'], 1)
        self.assertEqual(result['local']['median_ms'], 100)
        self.assertIsNone(result['gemini']['median_ms'])

    def test_missing_model_is_not_a_fake_local_translation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'experiments').mkdir()
            (root / 'experiments/local_comparison_cases.json').write_text(json.dumps({
                'source': 'test fixture', 'cases': [{'id': 'one', 'text': 'Hello.'}]}))
            with patch.object(benchmark, 'ROOT', root), patch.object(benchmark, 'NLLB', side_effect=ImportError('unavailable')), patch('sys.argv', ['test', '--providers', 'local', '--repeats', '1']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(benchmark.main(), 2)
            result = json.loads(next(root.glob('experiments/local_comparison/*/results.json')).read_text())
            self.assertEqual(result['models']['local']['status'], 'unavailable')
            self.assertEqual(result['rows'], [])
            self.assertEqual(result['summary'], {})

    def test_warmup_excluded_from_summary_and_no_visual_context(self):
        def response(url, payload=None):
            if payload is None: return {'provider': 'gemini', 'configured': True, 'model': 'test'}
            self.assertEqual(payload['previous_context'], '')
            return {'status': 'ok', 'translated_text': 'Test fixture only', 'latency_ms': 1, 'model': 'test'}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'experiments').mkdir()
            (root / 'experiments/local_comparison_cases.json').write_text(json.dumps({
                'source': 'test fixture', 'cases': [{'id': 'one', 'text': 'Hello.'}]}))
            with patch.object(benchmark, 'ROOT', root), patch.object(benchmark, 'request_json', side_effect=response), patch('sys.argv', ['test', '--providers', 'gemini', '--repeats', '2']), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(benchmark.main(), 0)
            result = json.loads(next(root.glob('experiments/local_comparison/*/results.json')).read_text())
            self.assertEqual(len(result['warmups']), 1)
            self.assertEqual(result['summary']['gemini']['attempts'], 2)
            self.assertEqual(result['unique_inputs'], 1)
            self.assertTrue(result['quality_score'].startswith('NOT_SCORED'))


if __name__ == '__main__': unittest.main()

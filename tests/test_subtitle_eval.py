import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from experiments.subtitle_eval import summarize_session


class SubtitleEvalTests(unittest.TestCase):
    def test_ready_and_display_are_separate(self):
        report = summarize_session({'version': 3, 'segments': [
            {'id': 1, 'session': 'a', 'sourceClockStartMs': 10000,
             'sourceClockEndMs': 12000, 'translationReadyAt': 13000,
             'shownAt': 15000, 'viewerDelayMs': 3000, 'status': 'committed'}]})
        self.assertEqual(report['metrics_ms']['ready_from_end']['median'], 1000)
        self.assertEqual(report['metrics_ms']['display_from_end']['median'], 3000)
        self.assertEqual(report['metrics_ms']['visible_start_offset']['median'], 2000)
        self.assertEqual(report['counts']['shown'], 1)

    def test_missing_failed_and_media_clocks_not_mixed(self):
        report = summarize_session({'version': 3, 'segments': [
            {'id': 1, 'session': 'a', 'mediaStart': 10, 'mediaEnd': 12,
             'translationReadyAt': 13000, 'status': 'committed'},
            {'id': 2, 'session': 'a', 'status': 'failed'},
            {'id': 3, 'session': 'a', 'status': 'pending'}]})
        self.assertEqual(report['counts']['total'], 3)
        self.assertEqual(report['counts']['failed'], 1)
        self.assertEqual(report['counts']['missing'], 1)
        self.assertEqual(report['counts']['unshown'], 3)
        self.assertIsNone(report['metrics_ms']['ready_from_end']['median'])
        self.assertEqual(report['metrics_ms']['ready_from_end']['missing_count'], 3)
        self.assertIsNone(report['quality']['wer'])
        self.assertEqual(report['quality']['status'], 'not_evaluated')

    def test_events_merge_by_session_and_keep_first_display(self):
        report = summarize_session({'version': 3, 'events': [
            {'type': 'source_committed', 'sessionId': 'a', 'segmentId': 1,
             'sourceClockStartMs': 10000, 'sourceClockEndMs': 12000},
            {'type': 'mt_returned', 'sessionId': 'a', 'segmentId': 1, 'clientNowMs': 13000},
            {'type': 'cue_selected', 'sessionId': 'a', 'segmentId': 1, 'clientNowMs': 14000},
            {'type': 'cue_selected', 'sessionId': 'a', 'segmentId': 1, 'clientNowMs': 16000},
            {'type': 'source_committed', 'sessionId': 'b', 'segmentId': 1},
            {'type': 'cue_skipped', 'sessionId': 'b', 'segmentId': 1, 'reason': 'overflow'}]})
        self.assertEqual(report['counts']['total'], 2)
        self.assertEqual(report['counts']['skipped'], 1)
        self.assertEqual(report['metrics_ms']['display_from_end']['median'], 2000)

    def test_invalid_order_is_excluded_and_counted(self):
        report = summarize_session({'segments': [{'id': 1, 'sourceClockStartMs': 10,
            'sourceClockEndMs': 20, 'translationReadyAt': 30, 'shownAt': 25}]})
        self.assertEqual(report['counts']['invalid_clock_order'], 1)
        self.assertEqual(report['metrics_ms']['display_from_end']['sample_count'], 0)

    def test_deadline_denominator_includes_failures_and_missing(self):
        report = summarize_session({'viewerDelayMs': 3000, 'segments': [
            {'id': 1, 'sourceClockStartMs': 0, 'translationReadyAt': 2000},
            {'id': 2, 'sourceClockStartMs': 0, 'status': 'failed'},
            {'id': 3, 'sourceClockStartMs': 0},
            {'id': 4, 'mediaStart': 0, 'translationReadyAt': 2000}]})
        self.assertEqual(report['ready_at_viewer_start'], {
            'comparable_count': 3, 'ready_count': 1, 'not_ready_count': 2,
            'unmeasured_count': 1, 'fraction': 1 / 3})

    def test_failed_return_is_not_success_latency(self):
        report = summarize_session({'events': [
            {'type': 'source_committed', 'sessionId': 'a', 'segmentId': 1,
             'sourceClockStartMs': 0, 'sourceClockEndMs': 1000},
            {'type': 'mt_returned', 'sessionId': 'a', 'segmentId': 1,
             'clientNowMs': 3000, 'status': 'failed', 'error': 'timeout'}]})
        self.assertEqual(report['counts']['failed'], 1)
        self.assertEqual(report['counts']['ready'], 0)
        self.assertIsNone(report['metrics_ms']['ready_from_end']['p95'])

    def test_percentile_and_missing_samples_are_explicit(self):
        segments = [{'id': number, 'sourceClockEndMs': 0,
                     'translationReadyAt': number} for number in range(1, 21)]
        segments.append({'id': 21, 'status': 'failed'})
        report = summarize_session({'segments': segments})
        self.assertEqual(report['metrics_ms']['ready_from_end'], {
            'median': 10.5, 'p95': 19, 'sample_count': 20, 'missing_count': 1})

    def test_cli_empty_session_is_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'session.json'
            output = Path(directory) / 'report.json'
            source.write_text(json.dumps({'version': 3, 'segments': [], 'events': []}))
            subprocess.run([sys.executable, 'experiments/subtitle_eval.py',
                            '--input', str(source), '--output', str(output)], check=True)
            report = json.loads(output.read_text())
            self.assertEqual(report['counts']['total'], 0)
            self.assertIsNone(report['presented_fraction'])


if __name__ == '__main__':
    unittest.main()

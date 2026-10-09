"""Summarize exported caption traces without inferring source/client clock maps.

All reported timings are milliseconds. Only sourceClockStartMs/EndMs explicitly
mapped to the browser clock are compared with translationReadyAt/shownAt.
Media seconds, Date.now timestamps, and backend durations are never substituted.
This is instrumentation coverage, not ground-truth speech or text coverage.
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _stats(values, total):
    ordered = sorted(values)
    return {
        'sample_count': len(ordered), 'missing_count': total - len(ordered),
        'median': statistics.median(ordered) if ordered else None,
        'p95': ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None,
    }


def summarize_session(payload):
    """Return JSON-safe counts and clock-qualified metrics for one export.

    Segments are keyed by (session, id); matching events supplement their fields.
    Missing means no successful readiness timestamp and no explicit failure.
    Unshown includes failed/missing/skipped cues. These overlapping counts are
    deliberately retained in the total denominator. p95 uses nearest rank.
    """
    if not isinstance(payload, dict):
        raise ValueError('Session export must be a JSON object')
    rows = {}
    default_session = payload.get('sessionId', payload.get('session'))
    for segment in payload.get('segments', []):
        if not isinstance(segment, dict) or segment.get('id') is None:
            raise ValueError('Each segment requires an id')
        key = (segment.get('session', segment.get('sessionId', default_session)), segment['id'])
        rows[key] = dict(segment)

    event_counts = Counter()
    skip_reasons = Counter()
    relevant = {'source_committed', 'mt_requested', 'mt_returned', 'mt_failed',
                'cue_selected', 'cue_hidden', 'cue_skipped', 'deadline_missed'}
    for event in payload.get('events', []):
        kind = event.get('type', 'unknown')
        event_counts[kind] += 1
        if kind == 'cue_skipped':
            skip_reasons[str(event.get('reason', 'unspecified'))] += 1
        if kind not in relevant or event.get('segmentId') is None:
            continue
        key = (event.get('sessionId', default_session), event['segmentId'])
        row = rows.setdefault(key, {})
        for field in ('sourceClockStartMs', 'sourceClockEndMs', 'viewerDelayMs',
                      'translationReadyAt', 'shownAt'):
            if _finite(event.get(field)) and not _finite(row.get(field)):
                row[field] = event[field]
        failed = (event.get('status') == 'failed' or event.get('success') is False
                  or bool(event.get('error')) or kind == 'mt_failed')
        if failed:
            row['status'] = 'failed'
        if kind == 'mt_returned' and not failed and not _finite(row.get('translationReadyAt')):
            row['translationReadyAt'] = event.get('clientNowMs')
        if kind == 'cue_selected':
            when = event.get('shownAt', event.get('clientNowMs'))
            if _finite(when) and (not _finite(row.get('shownAt')) or when < row['shownAt']):
                row['shownAt'] = when
        if kind == 'cue_skipped':
            row['_skipped'] = True
        if kind == 'deadline_missed':
            row['_deadline_missed'] = True

    total = len(rows)
    counts = dict.fromkeys(('total', 'ready', 'shown', 'failed', 'missing', 'unshown',
                           'skipped', 'deadline_missed', 'invalid_clock_order'), 0)
    counts['total'] = total
    samples = {name: [] for name in ('ready_from_start', 'ready_from_end',
               'display_from_end', 'ready_to_display', 'visible_start_offset',
               'absolute_visible_start_offset')}
    delay_samples = []
    deadline_comparable = deadline_ready = 0
    for row in rows.values():
        start, end = row.get('sourceClockStartMs'), row.get('sourceClockEndMs')
        ready, shown = row.get('translationReadyAt'), row.get('shownAt')
        failed = row.get('status') in ('failed', 'error')
        has_ready, has_shown = _finite(ready) and not failed, _finite(shown)
        counts['failed'] += failed
        counts['ready'] += has_ready
        counts['shown'] += has_shown
        counts['missing'] += not has_ready and not failed
        counts['unshown'] += not has_shown
        counts['skipped'] += bool(row.get('_skipped') or row.get('status') == 'skipped')
        invalid = ((_finite(start) and _finite(end) and end < start)
                   or (has_ready and has_shown and shown < ready))
        counts['invalid_clock_order'] += invalid
        counts['deadline_missed'] += bool(row.get('_deadline_missed'))
        if invalid:
            continue
        if has_ready and _finite(start):
            samples['ready_from_start'].append(ready - start)
        if has_ready and _finite(end):
            samples['ready_from_end'].append(ready - end)
        if has_shown and _finite(end):
            samples['display_from_end'].append(shown - end)
        if has_ready and has_shown:
            samples['ready_to_display'].append(shown - ready)
        delay = row.get('viewerDelayMs', payload.get('viewerDelayMs'))
        if _finite(delay) and delay >= 0:
            delay_samples.append(delay)
            if _finite(start):
                # Missing/failed translations fail the deadline when its clock
                # is known, rather than vanishing from this denominator.
                deadline_comparable += 1
                deadline_ready += has_ready and ready <= start + delay
                if has_shown:
                    offset = shown - (start + delay)
                    samples['visible_start_offset'].append(offset)
                    samples['absolute_visible_start_offset'].append(abs(offset))

    return {
        'schema_version': 1, 'input_version': payload.get('version'),
        'counts': counts, 'event_counts': dict(event_counts),
        'skip_reasons': dict(skip_reasons),
        'presented_fraction': counts['shown'] / total if total else None,
        'metrics_ms': {name: _stats(values, total) for name, values in samples.items()},
        'viewer_delay_ms': _stats(delay_samples, total),
        'ready_at_viewer_start': {
            'comparable_count': deadline_comparable, 'ready_count': deadline_ready,
            'not_ready_count': deadline_comparable - deadline_ready,
            'unmeasured_count': total - deadline_comparable,
            'fraction': deadline_ready / deadline_comparable if deadline_comparable else None,
        },
        'quality': {'status': 'not_evaluated', 'wer': None, 'deletion_rate': None,
                    'meaning_errors': None, 'terminology_errors': None, 'erasure': None,
                    'reason': 'Requires aligned reviewed references and/or explicit human annotations.'},
        'notes': [
            'p95 uses nearest rank; all timing values are milliseconds.',
            'Missing metric samples remain counted; success latency excludes failed requests.',
            'Coverage counts logged segments, not ground-truth speech or subtitle text.',
            'Source metrics require explicit sourceClockStartMs/sourceClockEndMs mappings.',
            'shownAt measures presenter selection, not photons or audible playback.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = summarize_session(json.loads(args.input.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()

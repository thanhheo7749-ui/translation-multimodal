import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.pilot_abc import ARMS, build_prompt, generate, run, validate, review_html, summarize


class PilotTests(unittest.TestCase):
    def row(self):
        return {"segment_id": "s1", "source_group": "lecture1", "start_sec": 1, "end_sec": 4,
            "frame_time_sec": 2, "frame_path": "frame.jpg", "audio_path": "audio.wav",
            "transcript_draft": "Draft", "transcript_gold": "This is the method.",
            "previous_context": "We introduce attention.", "manual_slide_text": "Attention mechanism",
            "ocr_text": "Attention mechanisrn", "reference_vi": "Đây là phương pháp đó.",
            "transcript_verified": True, "slide_verified": True, "reference_verified": True,
            "visual_need": "useful", "annotator_id": "r1"}

    def test_only_slide_evidence_changes(self):
        row = self.row()
        prompts = [build_prompt(row, arm) for arm in ARMS]
        instructions = [p.split("\nDữ liệu:\n")[0] for p in prompts]
        self.assertEqual(len(set(instructions)), 1)
        payloads = [json.loads(p.split("\nDữ liệu:\n")[1]) for p in prompts]
        self.assertEqual([p.pop("slide_text") for p in payloads], ["", row["manual_slide_text"], row["ocr_text"]])
        self.assertEqual(payloads[0], payloads[1]); self.assertEqual(payloads[1], payloads[2])

    def test_validation_rejects_future_unverified_and_external_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "frame.jpg").touch(); (base / "audio.wav").touch()
            row = self.row()
            self.assertEqual(validate({"segments": [row]}, base), [])
            row.update(frame_time_sec=120, transcript_verified=False, frame_path="../outside.jpg")
            errors = validate({"segments": [row]}, base)
            self.assertTrue(any("future frame" in e for e in errors))
            self.assertTrue(any("transcript_verified" in e for e in errors))
            self.assertTrue(any("frame_path" in e for e in errors))

    def test_empty_verified_slide_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "frame.jpg").touch(); (base / "audio.wav").touch()
            row = self.row(); row["manual_slide_text"] = ""
            self.assertEqual(validate({"segments": [row]}, base), [])

    def test_generation_rejects_truncation(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}]}
        class Client:
            def post(self, *a, **kw): return Response()
        with self.assertRaises(ValueError): generate(Client(), "model", "prompt")

    def test_generation_omits_thought_and_records_usage(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "reasoning", "thought": True}, {"text": "Bản dịch"}]}}], "usageMetadata": {"totalTokenCount": 10}}
        class Client:
            def post(self, *a, **kw): return Response()
        result = generate(Client(), "model", "prompt")
        self.assertEqual(result["text"], "Bản dịch")
        self.assertEqual(result["usage"]["totalTokenCount"], 10)

    def test_review_escapes_untrusted_text(self):
        row = self.row(); row["transcript_draft"] = "</textarea><script>alert(1)</script>"
        page = review_html({"preparation_id": "test", "segments": [row]})
        self.assertNotIn("</textarea><script>alert(1)</script>", page)

    def test_dry_run_makes_no_http_requests_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "frame.jpg").touch(); (base / "audio.wav").touch()
            row = self.row(); row["transcript_verified"] = False
            manifest = base / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 1, "study": "offline_ABC_feasibility", "segments": [row]}), encoding="utf-8")
            args = argparse.Namespace(manifest=manifest, output=base/"run", dry_run=True, model=None, timeout=30, seed=1)
            with patch("httpx.Client", side_effect=AssertionError("Network forbidden")):
                self.assertEqual(run(args), 0)
            summary = json.loads((args.output/"summary.json").read_text())
            self.assertEqual(summary["ok"], 0); self.assertEqual(summary["requests_planned"], 3)
            self.assertFalse((args.output/"blind_scores.csv").exists())
            with self.assertRaises(FileExistsError): run(args)

    def test_missing_key_sends_no_request_and_creates_no_run(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "frame.jpg").touch(); (base / "audio.wav").touch()
            manifest = base/"manifest.json"
            manifest.write_text(json.dumps({"schema_version": 1, "study": "offline_ABC_feasibility", "segments": [self.row()]}))
            args = argparse.Namespace(manifest=manifest, output=base/"run", dry_run=False, model="test-model", timeout=30, seed=1)
            with patch.dict("os.environ", {}, clear=True), patch("httpx.Client", side_effect=AssertionError("Network forbidden")):
                with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"): run(args)
            self.assertFalse(args.output.exists())

    def test_empty_scores_cannot_produce_quality_results(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base/"PRIVATE_arm_mapping.json").write_text("[]")
            (base/"manifest.snapshot.json").write_text(json.dumps({"schema_version": 1, "segments": [self.row()]}))
            scores=base/"scores.csv"; scores.write_text("sample_id,segment_id,rater_id,adequacy_1_to_5\n")
            args=argparse.Namespace(run_dir=base, scores=scores, output=base/"quality.json")
            with self.assertRaisesRegex(ValueError, "No complete"): summarize(args)
            self.assertFalse(args.output.exists())

    def test_summary_compares_only_complete_triplets_and_keeps_source_count(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mapping=[{"sample_id": f"p{i}", "segment_id": "s1", "arm": arm} for i,arm in enumerate(ARMS)]
            mapping.append({"sample_id": "partial", "segment_id": "s2", "arm": "A"})
            (base/"PRIVATE_arm_mapping.json").write_text(json.dumps(mapping))
            row2=self.row(); row2["segment_id"]="s2"
            (base/"manifest.snapshot.json").write_text(json.dumps({"schema_version":1,"segments":[self.row(),row2]}))
            scores=base/"scores.csv"
            scores.write_text("sample_id,segment_id,rater_id,adequacy_1_to_5\np0,s1,r,3\np1,s1,r,5\np2,s1,r,4\npartial,s2,r,5\n")
            args=argparse.Namespace(run_dir=base,scores=scores,output=base/"quality.json")
            summarize(args)
            result=json.loads(args.output.read_text())
            self.assertEqual(result["complete_triplets"],1)
            self.assertEqual(result["independent_sources"],1)
            self.assertEqual(result["paired_segments"][0]["B_minus_A"],2)
            self.assertEqual(result["paired_segments"][0]["C_minus_B"],-1)


if __name__ == "__main__":
    unittest.main()

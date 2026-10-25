import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from drift import DriftError, Organizer, digest, snapshot, validate_items


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "Downloads"
        self.root.mkdir()
        self.org = Organizer(self.root, self.base / "journal.sqlite3")

    def tearDown(self):
        self.org.db.close()
        self.temp.cleanup()

    def file(self, name="receipt.txt", content="Paid 42"):
        p = self.root / name
        p.write_text(content, encoding="utf-8")
        old = time.time() - 10
        os.utime(p, (old, old))
        return p

    def plan(self, bucket="receipts"):
        def infer(files, model, intention):
            return ([{"id": f["id"], "bucket": bucket, "reason": "Payment receipt evidence."} for f in files], {"model": model, "seconds": 0})
        with patch("drift.model_plan", side_effect=infer):
            return self.org.propose("test-model", "Group by purpose.")

    def test_move_and_undo_preserves_bytes(self):
        p = self.file()
        sha = digest(p)
        plan = self.plan()
        self.assertTrue(p.exists(), "Planning must not move anything")
        result = self.org.apply(plan["id"], ["f1"])
        dest = self.root / "_Drift/Receipts/receipt.txt"
        self.assertEqual(result["moved"], [p.name])
        self.assertFalse(p.exists())
        self.assertEqual(digest(dest), sha)
        self.org.undo(result["history"][0]["id"])
        self.assertEqual(digest(p), sha)
        self.assertFalse(dest.exists())

    def test_changed_file_invalidates_entire_batch(self):
        a, b = self.file("a.txt"), self.file("b.txt")
        plan = self.plan()
        b.write_text("different")
        with self.assertRaises(DriftError):
            self.org.apply(plan["id"], ["f1", "f2"])
        self.assertTrue(a.exists())
        self.assertTrue(b.exists())
        self.assertEqual(self.org.history(), [])

    def test_collision_does_not_overwrite(self):
        p = self.file()
        plan = self.plan()
        dest = self.root / "_Drift/Receipts/receipt.txt"
        dest.parent.mkdir(parents=True)
        dest.write_text("original target")
        with self.assertRaises(DriftError):
            self.org.apply(plan["id"], ["f1"])
        self.assertEqual(dest.read_text(), "original target")
        self.assertTrue(p.exists())

    def test_plan_single_use(self):
        self.file()
        plan = self.plan()
        self.org.apply(plan["id"], ["f1"])
        with self.assertRaises(DriftError):
            self.org.apply(plan["id"], ["f1"])

    def test_plan_expiry(self):
        self.file()
        plan = self.plan()
        plan["created"] -= 601
        with self.assertRaises(DriftError):
            self.org.apply(plan["id"], ["f1"])

    def test_only_selected_files_move(self):
        self.file("a.txt")
        self.file("b.txt")
        plan = self.plan()
        result = self.org.apply(plan["id"], ["f1"])
        self.assertEqual(result["moved"], ["a.txt"])
        self.assertTrue((self.root / "b.txt").exists())

    def test_model_failure_never_falls_back_to_rules(self):
        p = self.file()
        with patch("drift.model_plan", side_effect=DriftError("Model offline")):
            with self.assertRaises(DriftError):
                self.org.propose("missing-model", "Sort")
        self.assertIsNone(self.org.plan)
        self.assertTrue(p.exists())
        self.assertEqual(self.org.history(), [])

    def test_keep_cannot_be_moved(self):
        self.file()
        plan = self.plan("keep")
        with self.assertRaises(DriftError):
            self.org.apply(plan["id"], ["f1"])

    def test_failed_link_preserves_source_and_journal(self):
        p = self.file()
        plan = self.plan()
        with patch("drift.os.link", side_effect=OSError("Hardlinks unavailable")):
            result = self.org.apply(plan["id"], ["f1"])
        self.assertTrue(p.exists())
        self.assertTrue(result["errors"])
        self.assertEqual(self.org.history()[0]["state"], "failed")

    def test_undo_refuses_changed_destination(self):
        self.file()
        plan = self.plan()
        result = self.org.apply(plan["id"], ["f1"])
        (self.root / "_Drift/Receipts/receipt.txt").write_text("edited after move")
        with self.assertRaises(DriftError):
            self.org.undo(result["history"][0]["id"])

    def test_undo_refuses_occupied_original_name(self):
        self.file()
        plan = self.plan()
        result = self.org.apply(plan["id"], ["f1"])
        self.file(content="new original")
        with self.assertRaises(DriftError):
            self.org.undo(result["history"][0]["id"])
        self.assertEqual((self.root / "receipt.txt").read_text(), "new original")

    def test_path_escape_rejected(self):
        with self.assertRaises(DriftError):
            self.org.checked("../outside.txt")

    def test_no_recursive_scan(self):
        self.file()
        child = self.root / "project"
        child.mkdir()
        (child / "secret.txt").write_text("untouched")
        self.assertEqual(len(self.org.scan()["files"]), 1)

    def test_temporary_download_and_recent_file_skipped(self):
        self.file("partial.crdownload")
        (self.root / "still-writing.txt").write_text("partial")
        scan = self.org.scan()
        self.assertEqual(scan["files"], [])
        self.assertEqual(len(scan["skipped"]), 2)

    def test_excerpts_opt_in_and_bounded(self):
        self.file(content="x" * 900)
        self.assertNotIn("excerpt", self.org.scan()["files"][0])
        self.assertEqual(len(self.org.scan(True)["files"][0]["excerpt"]), 600)

    def test_batch_limit_is_visible(self):
        for i in range(14):
            self.file(f"{i:02}.txt")
        scan = self.org.scan()
        self.assertEqual(len(scan["files"]), 12)
        self.assertEqual(len(scan["skipped"]), 2)

    def insert_pending(self, state="prepared"):
        p = self.file()
        target = self.root / "_Drift/Receipts/receipt.txt"
        target.parent.mkdir(parents=True)
        self.org.db.execute("INSERT INTO moves (batch,root,source,destination,sha256,state,error,created) VALUES (?,?,?,?,?,?,?,?)", ("test", str(self.root), p.name, "_Drift/Receipts/receipt.txt", digest(p), state, "", "now"))
        self.org.db.commit()
        return p, target

    def test_recovery_rolls_back_interrupted_link(self):
        p, target = self.insert_pending()
        os.link(p, target)
        self.org.recover()
        self.assertTrue(p.exists())
        self.assertFalse(target.exists())
        self.assertEqual(self.org.history()[0]["state"], "failed")

    def test_recovery_recognizes_completed_move(self):
        p, target = self.insert_pending()
        os.link(p, target)
        p.unlink()
        self.org.recover()
        self.assertEqual(self.org.history()[0]["state"], "moved")

    def test_recovery_keeps_unresolved_conflict_visible(self):
        p, target = self.insert_pending()
        target.write_text("unrelated occupant")
        self.org.recover()
        row = self.org.history()[0]
        self.assertEqual(row["state"], "prepared")
        self.assertTrue(row["error"])
        self.assertTrue(p.exists())
        self.assertEqual(target.read_text(), "unrelated occupant")

    def test_interrupted_undo_is_recovered(self):
        p, target = self.insert_pending("undoing")
        os.link(p, target)
        p.unlink()
        os.link(target, p)  # Crash before unlinking the moved destination.
        self.org.recover()
        self.assertFalse(p.exists())
        self.assertTrue(target.exists())
        self.assertEqual(self.org.history()[0]["state"], "moved")

    def test_symlink_source_rejected_when_supported(self):
        p = self.file()
        try:
            (self.root / "linked.txt").symlink_to(p)
        except OSError:
            self.skipTest("Creating symlinks needs Windows developer mode/privilege")
        self.assertEqual(len(self.org.scan()["files"]), 1)
        self.assertEqual(len(self.org.scan()["skipped"]), 1)


class ModelValidationTests(unittest.TestCase):
    def test_valid_items(self):
        item = {"id": "f1", "bucket": "keep", "reason": "Insufficient context."}
        self.assertEqual(validate_items({"items": [item]}, {"f1"}), [item])

    def test_rejects_invalid_model_decisions(self):
        good = {"id": "f1", "bucket": "study", "reason": "Revision notes."}
        invalid = [[], {}, {"items": []}, {"items": [good, good]},
            {"items": [{**good, "bucket": "../../outside"}]},
            {"items": [{**good, "id": "f2"}]},
            {"items": [{**good, "reason": ""}]},
            {"items": [{**good, "reason": "x" * 241}]},
            {"items": [{**good, "path": "C:/Windows"}]},
            {"items": [{**good, "bucket": ["study"]}]}]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(DriftError):
                validate_items(raw, {"f1"})


if __name__ == "__main__":
    unittest.main()

"""Tests for memories_to_sqlite recipe.

Covers: UTC normalisation, surrogate stripping, path traversal guards,
idempotent upserts, envelope unwrapping, tag serialization, and SQL queryability.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Load memories_to_sqlite dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_sqlite.py"
spec = importlib.util.spec_from_file_location("memories_to_sqlite", script_path)
m2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2s)

load = m2s.load
text = m2s.text
tags_text = m2s.tags_text
utc_stamp = m2s.utc_stamp
strip_surrogates = m2s.strip_surrogates
validate_db_path = m2s.validate_db_path

SAMPLE_MEMORIES = [
    {
        "id": "mem_1",
        "content": "Prefers dark mode in code editors",
        "category": "lifestyle",
        "visibility": "private",
        "tags": ["preferences", "dev"],
        "source": "conversation",
        "created_at": "2026-09-20T10:00:00Z",
        "updated_at": "2026-09-20T10:05:00Z",
    },
    {
        "id": "mem_2",
        "content": "Working on autonomous bounty agents in Python and Rust",
        "category": "work",
        "visibility": "public",
        "tags": ["ai", "agents", "bounties"],
        "source": "cli",
        "created_at": "2026-09-21T14:30:00+02:00",
        "updated_at": "2026-09-21T14:35:00+02:00",
    },
]


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T10:00:00Z"), "2026-09-20 10:00:00")
        self.assertEqual(utc_stamp("2026-09-21T14:30:00+02:00"), "2026-09-21 12:30:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))
        self.assertEqual(utc_stamp("invalid-date"), "invalid-date")

    def test_strip_surrogates(self):
        cleaned = strip_surrogates("Note with \ud800 lone surrogate")
        self.assertEqual(cleaned, "Note with  lone surrogate")

    def test_text_coercion(self):
        self.assertIsNone(text(None))
        self.assertEqual(text("simple string"), "simple string")
        self.assertEqual(text({"key": "val"}), '{"key": "val"}')
        self.assertEqual(text(["a", "b"]), '["a", "b"]')
        self.assertEqual(text(123), "123")

    def test_tags_text_serialization(self):
        self.assertIsNone(tags_text(None))
        self.assertEqual(tags_text(["ai", "agents"]), '["ai", "agents"]')
        self.assertEqual(tags_text("single-tag"), "single-tag")
        self.assertEqual(tags_text({"k": "v"}), '{"k": "v"}')

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            validate_db_path(str(self.dir_path / ".." / "escape.sqlite"))

    def test_non_sqlite_file_refused(self):
        text_file = self.dir_path / "corrupt.sqlite"
        text_file.write_text("not a sqlite database", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_db_path(str(text_file))

    def test_load_and_query(self):
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, category, visibility, created_at FROM memories ORDER BY id")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "mem_1")
            self.assertEqual(rows[0][1], "Prefers dark mode in code editors")
            self.assertEqual(rows[0][2], "lifestyle")
            self.assertEqual(rows[0][3], "private")
            self.assertEqual(rows[0][4], "2026-09-20 10:00:00")

            self.assertEqual(rows[1][0], "mem_2")
            self.assertEqual(rows[1][2], "work")
            self.assertEqual(rows[1][4], "2026-09-21 12:30:00")
        finally:
            conn.close()

    def test_idempotent_import(self):
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        load(str(self.db_path), [str(json_file)])
        loaded2, added2, total2 = load(str(self.db_path), [str(json_file)])

        self.assertEqual(loaded2, 2)
        self.assertEqual(added2, 0)
        self.assertEqual(total2, 2)

    def test_wrapped_envelope_shapes(self):
        wrapped = {"memories": SAMPLE_MEMORIES}
        json_file = self.dir_path / "wrapped.json"
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(total, 2)

    def test_missing_id_raises_error(self):
        invalid = [{"content": "Memory without id"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(json_file)])

    def test_multi_page_merge(self):
        p1 = [{"id": "m1", "content": "Page 1 fact"}]
        p2 = [{"id": "m2", "content": "Page 2 fact"}]
        f1 = self.dir_path / "p1.json"
        f2 = self.dir_path / "p2.json"
        f1.write_text(json.dumps(p1), encoding="utf-8")
        f2.write_text(json.dumps(p2), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(f1), str(f2)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)


if __name__ == "__main__":
    unittest.main()

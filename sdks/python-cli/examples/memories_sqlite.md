# Convert a memories export to a SQLite database

Use this recipe when you want to query your Omi personal memories with SQL — filter
by category, search captured facts, run full-text search, or join against conversations and action items.
It reads one or more saved JSON exports, makes no network requests, and complements
[`memories_markdown.md`](memories_markdown.md) and [`conversations_sqlite.md`](conversations_sqlite.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.
The `python -m sqlite3` interactive shell examples below require Python 3.12+.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before importing. This is one page, not a
complete-account backup. To retrieve another page, increase `--offset` by 200
and use a different filename.

Run the importer:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py memories.json -o memories.db
```

Multiple pages can be merged in a single run:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py \
  memories_p1.json memories_p2.json memories_p3.json -o memories.db
```

Re-running with the same or updated exports is safe: the importer uses
`INSERT OR REPLACE` keyed on `id`, so rows are updated rather than duplicated.
The output path (`-o` or the positional fallback) must not contain `..`. If the
file already exists it must be a SQLite database; a non-SQLite file is refused
rather than overwritten.

## Schema

```sql
CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    content       TEXT,
    category      TEXT,
    visibility    TEXT,
    tags          TEXT,
    source        TEXT,
    created_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    updated_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    raw_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at);
```

All timestamps are normalised to UTC `YYYY-MM-DD HH:MM:SS` text so SQLite date
and time functions (`strftime`, `julianday`, `date`) work without coercion.
Tags are stored as JSON arrays or strings, compatible with SQLite `json_each()`.
The original record is kept verbatim in `raw_json` for `json_extract` queries.

## Example queries

```sh
python -m sqlite3 memories.db
```

Count memories by category:

```sql
SELECT category, COUNT(*) AS count
FROM memories
GROUP BY category
ORDER BY count DESC;
```

Find memories captured in the last 7 days:

```sql
SELECT content, category, created_at
FROM memories
WHERE created_at >= date('now', '-7 days')
ORDER BY created_at DESC;
```

Search memory contents for keywords:

```sql
SELECT id, category, content, created_at
FROM memories
WHERE content LIKE '%python%' OR content LIKE '%bounty%'
ORDER BY created_at DESC;
```

Find memories containing a specific tag using SQLite JSON functions:

```sql
SELECT id, category, content
FROM memories, json_each(tags)
WHERE json_each.value = 'work';
```

Extract nested properties from the original payload:

```sql
SELECT id, json_extract(raw_json, '$.category') AS raw_cat
FROM memories
LIMIT 5;
```

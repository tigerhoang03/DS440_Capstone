# FreshRSS connector (skeleton)

FreshRSS runs in PHP and typically uses MySQL/MariaDB (or sometimes SQLite).
Your professor wants its DB exposed so Python can read it.

Recommended approach:
1. Run FreshRSS in Docker (separate compose) and point it at MariaDB.
2. Create a read-only DB user.
3. Implement a Python reader that:
   - reads *only deltas* since last cursor
   - maps records into NormalizedItem
   - pushes into Redis stream

Add files here:
- `schema_notes.md` (your notes on the tables you need)
- `reader.py` (async SQLAlchemy reader against MariaDB)

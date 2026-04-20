# RSSGuard connector (skeleton)

RSSGuard often stores data in SQLite.
Implement an SQLite reader that:
- queries new items since last seen ID or timestamp
- maps into NormalizedItem
- publishes into Redis stream

Notes:
- SQLite concurrency is limited; use WAL mode if needed.
- Consider using RSSGuard's own export features if DB schema changes.

# a2moto

Full specification: @docs/SPEC.md

## Environment
- Windows, PowerShell 5.1. No `&&` chaining. Use `;` between commands.
- Use pathlib.Path everywhere. Never string-concatenate paths.
- Close SQLite connections explicitly; Windows file locking is stricter.

## Non-negotiable
- Respect robots.txt. Rate limit 1 req / 2s per domain. Never bypass captchas or login walls.
- Cache every raw HTTP response to disk. Parsers must run offline from cache.
- One scraper failure must not abort the run.
- Every text extractor needs a test against a real fixture before it counts as done.
- Build in the order given in SPEC.md. Do not skip ahead.
- Conda env `a2moto` is active. Install with pip inside it. Do not create a .venv.

Rules for this repo:
- Never invent data values. If a value can't be fetched or found, stop and tell me.
- Never commit API keys. Read keys from .env.
- Follow SPEC.md exactly; ask before changing the schema, tag fields, tool descriptions, or the question file.
- Scope is Version 2: 4 companies (CMG, WING, YUM, DRI), 42 questions, 504 runs. No auto-tagging, no case study PDF.
- semantics.py is the only place aggregation rules live.
- The eval answer key must never be computed with semantics.py.
- Agents get read-only DuckDB access.
- Never change a test's expected value to make it pass.
- Every phase ends by running its acceptance checks and showing the output. Then stop.

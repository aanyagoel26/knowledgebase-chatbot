Replace this file in your project:

app/services/database/database_assistant_service.py

Fixes included:
- No default is_active = TRUE filter.
- Active/inactive filter is added only when user explicitly asks.
- AIML/HR/IT/Finance department filters are deterministic.
- Name-only, email-only, count queries handled safely.
- Admin users are not hidden unless user explicitly filters/excludes them.
- LLM SQL prompt updated with stricter rules.

After replacing, restart:
uvicorn main:app --reload

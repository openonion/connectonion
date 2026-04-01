<!--
name: 'Skill: Build with Claude API (reference guide)'
description: Template for presenting language-specific reference documentation with quick task navigation
ccVersion: 2.1.83
-->
## Reference Documentation

The relevant documentation for your detected language is included below in `<doc>` tags. Each tag has a `path` attribute showing its original file path. Use this to find the right section:

### Quick Task Reference

**Single text classification/summarization/extraction/Q&A:**
→ Refer to `{lang}/claude-api/README.md`

**Chat UI or real-time response display:**
→ Refer to `{lang}/claude-api/README.md` + `{lang}/claude-api/streaming.md`

**Long-running conversations (may exceed context window):**
→ Refer to `{lang}/claude-api/README.md` — see Compaction section

**Prompt caching / optimize caching / "why is my cache hit rate low":**
→ Refer to `shared/prompt-caching.md` + `{lang}/claude-api/README.md` (Prompt Caching section)

**Function calling / tool use / agents:**
→ Refer to `{lang}/claude-api/README.md` + `shared/tool-use-concepts.md` + `{lang}/claude-api/tool-use.md`

**Batch processing (non-latency-sensitive):**
→ Refer to `{lang}/claude-api/README.md` + `{lang}/claude-api/batches.md`

**File uploads across multiple requests:**
→ Refer to `{lang}/claude-api/README.md` + `{lang}/claude-api/files-api.md`

**Agent with built-in tools (file/web/terminal) (Python & TypeScript only):**
→ Refer to `{lang}/agent-sdk/README.md` + `{lang}/agent-sdk/patterns.md`

**Error handling:**
→ Refer to `shared/error-codes.md`

**Latest docs via WebFetch:**
→ Refer to `shared/live-sources.md` for URLs

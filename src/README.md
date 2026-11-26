# Selected source files

Real files copied from the private Neural Hub Institute repository, kept at their original paths so imports read naturally.
They are here to be read, not built: the rest of the app (other modules, config, database) is private.

- `frontend/` — Next.js 16 / React 18 / TypeScript components and typed API clients
- `backend/` — FastAPI modules: the AI layer (LLM gateway, AI Teacher policy and lesson flow, course pipeline, fact check,
  Ask-AI intent, class notes, teacher AI) and core business logic (booking, certificates)

No secrets are included: every key is read from environment variables.

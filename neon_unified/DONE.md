Version 1.0 Done Checklist
==========================

- GenAgent._call handles 429 without NameError (openai imported, OPENAI_ERRORS defined)
- success is true only when tests ran and passed (strict logic in GenerationOrchestrator.generate)
- smoke_test.py passes (23/23 offline tests green)
- one short generate (habit tracker) can complete without crashing on errors (verified by compilation + smoke tests)
- no new features added in this session (only fixes to generation_core.py and DONE.md)

# RESIDUAL RISKS -- Post-Audit

## 1. crypto-trader-v1_1: 6,961-line Monolith
- Risk: 20+ global Maps without TTL/size limits -> memory exhaustion in production
- Mitigation: Apply TTLCache pattern (FIX 7, 15, 24) + periodic cleanup jobs
- Unavoidable: Refactoring to modular architecture would take weeks

## 2. api_money_bot_complete: DOM Intelligence Fragility
- Risk: Regex-based classification has false positives; website changes break harvesters
- Mitigation: Add confidence scoring, fallback selectors, visual regression tests
- Unavoidable: Without ML classifier, will always need maintenance

## 3. neon_architect Variants (3 projects): Code Duplication
- Risk: Bug fixes must be applied to 4 separate copies (neon_unified, emergentsh, ases_v3_1, antigravity-kandover)
- Mitigation: Extract shared TokenBucket/GenAgent/ProviderPool to common library
- Unavoidable: Current architecture has 380KB duplicate per project

## 4. solana-auto-trader-live-llm: Live Trading Financial Risk
- Risk: Any position management bug = direct financial loss
- Mitigation: Paper trading validation, kill switches, position size limits, audit trail
- Unavoidable: Live trading always carries execution risk

## 5. guardian_app: Flutter/Dart Unverified
- Risk: No static analysis on Dart code (Dart SDK not installed)
- Mitigation: Install Dart SDK, run dart analyze, flutter test
- Unavoidable: Requires external tooling

## 6. OMEGA / convergence_framework: Not Self-Contained
- Risk: Missing packages (omega_agent), duplicate test modules
- Mitigation: Include package sources or remove shims; restructure tests
- Unavoidable: These are framework components, not standalone products

## 7. Free-tier NIM RPM Limits (neon_unified)
- Risk: 40 RPM = physics limit on multi-hour Emergent-style runs
- Mitigation: 45s+ post-429 backoff implemented; need paid tier for sustained runs
- Unavoidable: Cannot code around quota limits

## 8. Test Coverage Gaps
- Projects with NO tests: antigravity-kandover, solana-auto-trader, guardian_app, ai_video_monetizer
- Risk: Regressions undetected
- Mitigation: Add at least smoke tests for critical paths

## 9. Credential Handling
- Risk: Some projects read secrets from env without validation at startup
- Mitigation: Added startup validation in FIX 21, 22
- Unavoidable: Secret rotation not implemented

## 10. Concurrency / Race Conditions
- Risk: Multiple global state Maps in crypto-trader accessed from async paths without locks
- Mitigation: TypeScript has no native mutex; consider architectural redesign
- Unavoidable: Requires significant refactor

---

## ACCEPTABLE RISK LEVELS

| Project | Production Ready? | Caveats |
|---------|------------------|---------|
| neon_unified | YES (with quota disclaimer) | Free-tier RPM limits |
| ases_v3_1 | YES | TDD coverage excellent |
| OMEGA | YES (if package included) | Shim needs resolution |
| voice_agent_avatar | YES (with env validation) | Free stack needs Kaggle deps |
| convergence_framework | YES (as library) | Not a standalone product |
| guardian_app | CONDITIONAL | Needs Dart analysis |
| ai_video_monetizer | CONDITIONAL | Scripts need testability |
| crypto-trader-v1_1 | CONDITIONAL | Memory leaks, monolith |
| api_money_bot_complete | CONDITIONAL | Fragile DOM parsing |
| solana-auto-trader | CONDITIONAL | Live money risk |
| emergentsh/antigravity | CONDITIONAL | Duplicate neon_architect |

---

## RECOMMENDATION

Ship these 4 THIS WEEK (revenue potential: 15-30K):
1. ases_v3_1 (3,999) - Best test coverage
2. OMEGA (3,999) - If package included
3. Neon Unified (2,999) - With free-tier disclaimer
4. Voice Agent Avatar (2,999) - With env validation

Fix and ship NEXT WEEK:
5. guardian_app (7,999-12,999) - After Dart analysis
6. convergence_framework - As component

Park (study kits only):
- crypto-trader-v1_1 (monolith needs refactor)
- api_money_bot_complete (fragile, maintenance heavy)
- solana-auto-trader (live money liability)
- antigravity-kandover (duplicate)

Use revenue to fund refactors.

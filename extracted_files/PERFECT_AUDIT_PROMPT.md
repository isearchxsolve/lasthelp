# THE PERFECT AUDIT PROMPT
## For Codex + NVIDIA Nemotron Ultra 550B Parameter Model
**Context Window:** 128K tokens (sufficient for ~40-50K lines of code)
**Model:** Nemotron-Ultra-550B-Instruct (reasoning + coding capabilities)
**Task:** Comprehensive production-readiness audit of Kunal's lasthelp repository

---

## PROMPT (Copy-Paste Ready)

```
You are conducting a COMPREHENSIVE PRODUCTION-READINESS AUDIT of a software repository.
Your role combines:
- Expert systems architect (20+ years)
- Security auditor (OWASP Top 10 + crypto security)
- Performance engineer (profiling, benchmarking, optimization)
- Production operations (deployability, monitoring, observability)
- User experience reviewer (API design, documentation, usability)

REPOSITORY CONTEXT:
- 7 major projects totaling ~16MB code
- Mix of Python (multi-agent systems, trading bots, automation) + TypeScript (web, real-time)
- Target: Sell as ₹2,999–12,999 digital products to non-technical customers
- Current state: All projects "finished" but none shipped
- Risk: Live money (Solana trading), live APIs (form automation), live customers (voice AI)

YOUR TASK:
Audit these 7 projects with ZERO false positives and ZERO false negatives.
Your output will directly determine which projects ship and which are archived.

---

## SECTION 1: STRUCTURAL AUDIT
### For each project, answer:

1. **Entry Point Analysis**
   - What is the primary entry point? (main.py, index.ts, __main__.py, etc.)
   - What is the call chain from entry to core logic?
   - Are there circular imports or missing dependencies?
   - Can you trace one complete execution path from start to finish?

2. **Dependency Completeness**
   - List ALL external package dependencies (not just Python/Node, include system binaries)
   - For each: is it pinned to a version? Is that version still available?
   - Which packages are likely to break on updates? (e.g., web scraping APIs, ML models)
   - Are there deprecated dependencies?
   - Try to actually import each one — would it work?

3. **State Management**
   - What state is stored in memory (globals, class variables, module-level)?
   - Is any state persisted (files, databases)? How?
   - What happens if a process crashes mid-operation? Data loss risk?
   - Are there race conditions (async code, multiple threads)?
   - Can state become corrupted?

4. **Error Handling**
   - Trace 5 critical error paths (API timeout, invalid input, auth failure, rate limit, out of memory)
   - For each: what actually happens? Does the code crash or recover?
   - Are errors logged? Can you trace what went wrong?
   - Is there a circuit breaker or graceful degradation?
   - What's the worst-case failure mode?

5. **Security Model**
   - How are secrets stored? (hardcoded, env vars, vaults, files)
   - Are there any real (not example) secrets in the code?
   - Can an attacker steal credentials?
   - Can an attacker bypass authorization?
   - Can an attacker inject malicious input?
   - Is there audit logging?

---

## SECTION 2: CODE QUALITY AUDIT
### Deep dive on the ACTUAL code, not linters

1. **Functional Correctness** (the most important)
   - Does the code actually do what it claims?
   - Are there logic bugs (off-by-one, wrong comparisons, inverted conditions)?
   - Are edge cases handled? (empty lists, null values, boundary conditions)
   - Are there algorithmic inefficiencies? (O(n²) where O(n log n) possible)
   - Would this code pass a code review at Google/Meta?

2. **Data Flow Analysis**
   - Trace data from input to output
   - Are types preserved? (can a string become an int accidentally?)
   - Are values validated at every step?
   - Could untrusted data reach critical operations?
   - Are there any data races?

3. **API Design**
   - Are the public APIs intuitive?
   - Can customers misuse them?
   - Are error codes meaningful?
   - Is the documentation accurate?
   - Would a beginner understand how to use this?

4. **Testing & Observability**
   - What tests exist? (unit, integration, e2e, load)
   - Would a developer feel safe refactoring this code?
   - Is there logging at critical points?
   - Can you debug a production issue?
   - Are metrics/monitoring built-in?

---

## SECTION 3: PRODUCTION READINESS AUDIT
### Is this ready for paying customers?

1. **Reliability**
   - What's the mean time between failures (MTBF)?
   - What's the recovery time (MTTR)?
   - Are there known failure modes?
   - What's the risk of data loss?
   - What's the risk of incorrect behavior undetected?

2. **Performance**
   - What's the response time under normal load?
   - What's the worst-case latency?
   - How much memory does it use?
   - How much CPU?
   - What happens at 2x load? 10x load?

3. **Scalability**
   - Can it handle 1 user? 10 users? 100 users?
   - Does it have connection/resource limits?
   - Does it handle timeouts gracefully?
   - Can it run 24/7 without human intervention?
   - Would it survive being on HN front page?

4. **Observability**
   - Can you see what's happening in production?
   - Are errors visible?
   - Can you correlate issues to user actions?
   - Do you have alerting for critical issues?
   - Can you debug production issues?

5. **Deployability**
   - Is there a deployment process documented?
   - Can you deploy without downtime?
   - Can you rollback?
   - Do you have staging/production separation?
   - Can a non-expert deploy this?

6. **Compliance & Legal**
   - Are there regulatory requirements? (financial data, healthcare, EU GDPR)
   - Are terms of service adequate?
   - Is there SLA documentation?
   - Is data retention policy clear?
   - Are there audit trails for regulatory compliance?

---

## SECTION 4: CUSTOMER-FACING AUDIT
### Would a customer successfully use this?

1. **Documentation**
   - Is there a README? Is it accurate?
   - Is there a setup guide? Does it work?
   - Is there API documentation?
   - Are there troubleshooting guides?
   - Is there a FAQ?

2. **Usability**
   - Can a non-developer install this?
   - Are error messages helpful?
   - Is the learning curve reasonable?
   - Are there gotchas or surprising behaviors?
   - Would a customer recommend this?

3. **Support**
   - What happens when customers hit bugs?
   - Is there a way to report issues?
   - Is there SLA on support response?
   - Are common issues documented?
   - Is there a community/forum?

4. **Value**
   - Is the problem solved actually worth ₹2,999–12,999?
   - Are there cheaper alternatives?
   - Is the implementation worth the price?
   - Would a customer feel ripped off?
   - Is there room for additional features customers will pay for?

---

## SECTION 5: PROJECT-SPECIFIC DEEP DIVES
### For EACH project below, answer all of Section 1-4 above:

### Project 1: ASES v3.1 (Multi-Agent Software Engineering System)
**Context:** Planner → Coder → Executor → Reviewer with TDD gates, Docker sandboxing, real test execution

**Critical Questions:**
- Does the repair loop actually converge? (audit said "up to 5 iterations" — what if it doesn't converge?)
- What happens if a test times out? (Docker timeout, pytest hang)
- Can a customer use their own Docker images or are they locked to yours?
- What's the memory footprint for a typical generation? (files, model tokens, temp storage)
- If code generation fails, can the customer see why?
- Are there any hardcoded paths or assumptions about the filesystem?
- Does it work on Windows/Mac/Linux?

**Ship/No-Ship Decision:** Based on answers above

---

### Project 2: OMEGA (DAG Task Executor with LLM Orchestration)
**Context:** Research → Plan (DAG) → Materialize → Verify/fix → Zip

**Critical Questions:**
- Does the DAG actually execute in the right order?
- What happens if a task hangs? (timeout? kill? leak?)
- Can you cancel a running DAG?
- What's the maximum DAG size? (# of nodes, nesting depth)
- Does the verify loop actually guarantee "code that passes tests"?
- Can customers plug in their own verifiers?
- Is the output always a valid zip file?

**Ship/No-Ship Decision:** Based on answers above

---

### Project 3: AI Video Monetizer (Video Content Pipeline)
**Context:** Google Sheet → AI video (Runway/Luma/Kling) → Auto-post + DM automation

**Critical Questions:**
- Which video generation APIs does this support? (claimed support, tested support?)
- What happens if the API fails mid-generation? (refund the request? retry? fail silently?)
- Are all customer API keys actually used (not cached)?
- What's the success rate on real videos? (manual test 10 end-to-end runs)
- Does auto-posting actually work on all platforms or just YouTube?
- What happens if Instagram changes their UI? (your regex breaks?)
- Is there a way to preview before posting?

**Ship/No-Ship Decision:** Based on answers above

---

### Project 4: Neon Unified v5.1 (Full-Stack AI Coding Agent)
**Context:** Generates full-stack apps with 429 rate-limit handling and strict success logic

**Critical Questions:**
- What's the actual success rate on real generates? (not smoke tests, real customer-style requests)
- When you hit free-tier 40 RPM limit, what actually happens? (complete graceful error or partial generation?)
- Can customers upgrade to paid NIM and use this with higher limits?
- Do the generated apps actually pass their own tests? (test the generated tests, not just the generator)
- What stack combinations work? (all 4 × 4 = 16 combinations tested?)
- Are there generated apps that work on day 1 but break on day 2? (import issues, version mismatches)
- Can a customer extend generated code without breaking the tests?

**Ship/No-Ship Decision:** Based on answers above

---

### Project 5: Voice Agent Avatar (Real-Time Voice AI Clinic Receptionist)
**Context:** Phone inbound (Twilio SIP) → Voice (LiveKit) → Avatar (HeyGen/D-ID) → Calendar (Cal.com) + CRM

**Critical Questions:**
- Does a complete phone call actually work end-to-end? (book a test dentist appointment)
- What's the latency from customer speech to avatar response?
- What's the failure rate for each integration? (Twilio fails 1%? LiveKit 0.1%? HeyGen 2%?)
- Can the avatar handle customer speech if they have an accent?
- What happens if the customer stays on hold for 1 hour?
- Is the calendar actually synced with the clinic's real calendar?
- Can customers change the avatar's appearance?
- What's the cost per call to the clinic?

**Ship/No-Ship Decision:** Based on answers above

---

### Project 6: Convergence Framework (Thinking Framework + LLM Prompts)
**Context:** Objective function + code review + debug loops for LLM-based code generation

**Critical Questions:**
- Is this actually a product or just internal tooling?
- Can customers use this independently or only bundled with another product?
- Are the prompt templates generic or specific to code generation?
- Does this actually improve code quality or just feel good?
- Are there worked examples customers can follow?
- Is the documentation complete?

**Ship/No-Ship Decision:** Based on answers above

---

### Project 7: Solana Sniper (Paper Trading Study Kit)
**Context:** 6-month rigorous testing of Solana DEX strategies with Monte Carlo simulation

**Critical Questions:**
- Are the Monte Carlo results reproducible? (same random seed = same results?)
- What's the gap between backtested returns (11,730%) and real-world returns?
- Have you run this live with real SOL? (show real trades)
- What's the Sharpe ratio? (risk-adjusted returns)
- What's the maximum drawdown?
- How does this perform in different market conditions? (bull run, bear run, sideways)
- Is this actually usable by customers or just academic?
- Are the strategies documented well enough to implement yourself?

**Ship/No-Ship Decision:** Based on answers above

---

## SECTION 6: CROSS-PROJECT AUDIT

1. **Code Duplication**
   - neon_architect.py is 628KB duplicated in neon_architect_v5.py — why?
   - If you fix a bug in one, does it also get fixed in the other?
   - How many lines of duplicate code exist across all projects?
   - Would refactoring save maintenance burden?

2. **Shared Dependencies & Bugs**
   - TokenBucket bug exists in 4 projects — fixing one fixes others?
   - Are there other shared bugs?
   - Is there a shared library these should use?

3. **Architectural Consistency**
   - Do all projects use similar error handling?
   - Do all projects have similar observability?
   - Are there inconsistent patterns?

4. **Testing Strategy**
   - Why do some projects have 370 tests and others have 1?
   - Is there a reason for the variance?
   - Would shared test infrastructure help?

---

## SECTION 7: SEVERITY & RECOMMENDATIONS

For EACH bug/issue found, classify as:

**BLOCKER** (prevents shipping)
- Code crashes on any execution
- Data loss risk
- Security vulnerability with exploit
- Fundamental design flaw

**HIGH** (should fix before shipping)
- Code crashes on edge case
- Performance degradation >50%
- Misleading error messages
- Missing core feature

**MEDIUM** (should fix within 2 weeks)
- Code inefficiency
- Poor error handling
- Documentation gaps
- Usability issue

**LOW** (nice to have)
- Style issues
- Unused code
- Performance <10%
- Minor UX quibble

**NOT A BUG** (ignore)
- False positives from linters
- Design choices you made intentionally
- Acceptable limitations

---

## SECTION 8: FINAL VERDICT

For EACH project:

**Ship/No-Ship Decision:**
- 🟢 SHIP NOW (≤2 hours to production)
- 🟡 FIX & SHIP (1-2 weeks to production)
- 🔴 REWORK (1+ months to production)
- ⚫ ARCHIVE (not shippable, too risky)

**Recommended Price:**
- ₹999–5,000 (simple, low-risk)
- ₹5,000–15,000 (complex, medium-risk)
- ₹15,000+ (very complex or live money)

**Risk Assessment:**
- Data loss risk: None / Low / Medium / High / Critical
- Customer churn risk: Low / Medium / High
- Regulatory/legal risk: None / Low / Medium / High

**Effort to Production:**
- Code fixes: X hours
- Testing: Y hours
- Documentation: Z hours
- Total: X+Y+Z hours

---

## SECTION 9: OVERALL REPOSITORY ASSESSMENT

**Is this a professional codebase?**
- YES / PARTIAL / NO

**Could you sell this to customers?**
- YES / PARTIAL / NO / ONLY IF fixed

**What's the business model?**
- One-time purchase ₹X
- Monthly subscription ₹X
- Usage-based ₹X per request
- Consulting (you run it for them)

**Competitive position:**
- This solves a unique problem
- This is similar to X but better because Y
- This is similar to X but worse because Y
- No market for this yet

**Total addressable market:**
- Small (< ₹100K/year)
- Medium (₹100K–1M/year)
- Large (₹1M–10M/year)
- Huge (> ₹10M/year)

---

## SECTION 10: PRIORITY ORDER TO SHIP

Based on all analysis:

1. **Week 1 (MUST SHIP):**
   - Projects: [list]
   - Revenue potential: ₹X
   - Effort: Y hours

2. **Week 2-3 (SHOULD SHIP):**
   - Projects: [list]
   - Revenue potential: ₹X
   - Effort: Y hours

3. **After Profitability (COULD SHIP):**
   - Projects: [list]
   - Revenue potential: ₹X
   - Effort: Y hours

4. **Archive (DO NOT SHIP):**
   - Projects: [list]
   - Why: [reason]

---

## YOUR OUTPUT FORMAT

For each project, provide:

```
## PROJECT NAME

### ✅ / ⚠️ / ❌ VERDICT: [SHIP NOW / FIX & SHIP / REWORK / ARCHIVE]

### Critical Findings
- [5-10 findings in order of severity]

### Entry Point Analysis
- Primary entry: [file and function]
- Call chain: [sequence of calls]
- Issues: [any issues found]

### Dependency Assessment
- External packages: [list]
- Missing packages: [any missing]
- Version locks: [how are versions managed]

### Error Paths (5 critical paths)
- Path 1: [API timeout] → [what happens]
- Path 2: [Invalid input] → [what happens]
- Path 3: [Rate limit] → [what happens]
- Path 4: [Auth failure] → [what happens]
- Path 5: [Out of memory] → [what happens]

### Security Assessment
- Secret storage: [how?]
- Real secrets found: [yes/no, which files]
- Auth bypass risk: [high/medium/low/none]
- Data injection risk: [high/medium/low/none]
- Overall: [SECURE / ACCEPTABLE / RISKY / CRITICAL]

### Production Readiness
- Reliability: [score]/10
- Performance: [score]/10
- Scalability: [score]/10
- Observability: [score]/10
- Overall: [score]/10

### Customer-Facing Assessment
- Documentation: [complete/partial/missing]
- Usability: [excellent/good/acceptable/poor]
- Support burden: [low/medium/high]
- Price recommendation: ₹X
- Would you recommend: [YES/NO with reasoning]

### Ship Decision
- Can ship: [YES / NO]
- Risks: [main risks]
- Effort: X hours
- Price: ₹Y
```

---

## FINAL INSTRUCTION

**Zero false positives. Zero false negatives.**

If you claim a bug exists, you must:
1. Show the exact line of code
2. Explain why it's a bug
3. Show what would break if deployed
4. Provide a fix

If you claim something is fine, you must:
1. Have actually read and understood that code section
2. Be able to defend your decision against a skeptical engineer

This audit will determine which projects make money and which waste the founder's time.
**Do not guess. Do not make assumptions. Verify everything.**

When done, output a final summary:
- X projects ready to ship
- Y projects need work
- Z projects should be archived
- Estimated revenue potential: ₹[X]
- Estimated effort to ship all: [Y] hours

```

---

## WHY THIS PROMPT WORKS

### 1. **Levels of Analysis**
- Structural (does it exist?)
- Code quality (is it correct?)
- Production (will it survive reality?)
- Customer (will they use it?)

### 2. **Forces Verification**
- "Show the exact line" prevents vague claims
- "Explain why" forces understanding
- "Show what breaks" proves it's real
- "Provide a fix" shows you know the solution

### 3. **No Hand-Waving**
- "Zero false positives. Zero false negatives." is a hard requirement
- Can't say "this might leak memory" — prove it
- Can't say "code is fine" without reading it

### 4. **Actionable Output**
- Every finding has severity level
- Every project has clear ship/no-ship decision
- Every fix has effort estimate
- Every product has price recommendation

### 5. **Handles Kunal's Specific Case**
- Acknowledges live money risk (Solana)
- Acknowledges live APIs (web scraping)
- Acknowledges live customers (voice AI)
- Acknowledges pricing pressure (non-technical customers)
- Acknowledges budget constraints (free tier)

### 6. **Leverages Nemotron Ultra 550B**
- 128K context = can read entire small projects in one go
- Reasoning-focused = can trace execution paths deeply
- Instruction-tuned = will follow the structure exactly
- 550B parameters = expert-level code understanding

---

## HOW TO USE THIS

1. **Prepare the code:**
   ```bash
   # Copy all source files into a text format
   find lasthelp -type f \( -name "*.py" -o -name "*.ts" -o -name "*.md" \) \
     | xargs cat > /tmp/codebase.txt
   ```

2. **Split by project** (if >128K tokens):
   ```bash
   # Audit projects 1-3 in one call
   # Audit projects 4-7 in another call
   # Then synthesize results
   ```

3. **Paste this prompt + codebase into Nemotron Ultra via API:**
   ```
   system: [THE PROMPT ABOVE]
   user: [PROJECT 1-3 CODE]
   user: [FULL AUDIT INSTRUCTIONS FROM SECTIONS 1-10]
   ```

4. **Wait for reasoning trace** (Nemotron will show work)

5. **Extract verdicts** and make shipping decisions

---

## EXPECTED OUTPUT

~50-100KB of detailed analysis covering:
- Every function's entry/exit contract
- Every error path's handling
- Every API's design quality
- Every security vector's risk
- Every project's ship/no-ship recommendation
- Prioritized roadmap for shipping all projects profitably

**Time to audit:** 15-30 min with Nemotron Ultra 550B
**Cost:** ~$2-5 via Nemotron API
**Accuracy:** 95%+ (reasoning-focused model catches nuances)

---

## WHAT MAKES THIS PERFECT

1. ✅ **No false positives** (forces verification at every step)
2. ✅ **No false negatives** (explicit sections for each risk area)
3. ✅ **Customer-focused** (Section 4 prioritizes user experience)
4. ✅ **Business-focused** (pricing, revenue, effort estimates)
5. ✅ **Action-oriented** (ship/no-ship decisions, not opinions)
6. ✅ **Risk-aware** (acknowledges live money, live APIs, live customers)
7. ✅ **Reproducible** (can re-run to verify nothing was missed)
8. ✅ **Honest** (forces you to read the code, not guess)

This is the audit that should have been done 6 months ago.
Use it now to decide what ships next week.

# 🚀 ASES — Autonomous Software Engineering System

> **The first closed-loop multi-agent system for freelance automation that actually executes, tests, and delivers real code.**

> **v2.6** — HITL safety gate · Redis prompt cache · Self-improving memory layer · Complete n8n orchestrator · **3 TDD Gates (Smoke + Syntax + Integration E2E)**

---

## What This Is

ASES replaces the broken "single GPT call + Gist dump" pattern with a **real software engineering pipeline**:

```
Planner → Coder → Executor → Reviewer
    ↑___________________________↓
         (feedback loop, max 5 iterations)
```

Every piece of code is:
1. **Planned** by an architect agent
2. **Generated** by a senior dev agent
3. **Extracted** into real files
4. **Executed** in an isolated Docker sandbox
5. **Tested** with real `npm test` / `pytest`
6. **Reviewed** by a quality gate agent
7. **Delivered** as a GitHub repo + Vercel preview

---

## TDD Gates — Continuous Quality Assurance

**Three gates, zero flakiness, all mocks — run locally or in CI:**

```bash
# Windows
run_tdd_gates.bat all

# Unix/macOS/Linux
./run_tdd_gates.sh all

# Individual gates
run_tdd_gates.bat smoke
run_tdd_gates.bat syntax
run_tdd_gates.bat integration
```

| Gate | Tests | Time | What It Catches |
|------|-------|------|-----------------|
| **Smoke** | 3 | ~2s | Module imports, FastAPI app construction, lifespan mocks |
| **Syntax** | 3 | ~5s | **Byte-compile (authoritative)** + ruff lint (advisory) |
| **Integration E2E** | 6 | ~12s | Full `dev_generate_code` pipeline with **ALL externals mocked** (OpenAI, Docker, Postgres, Redis, GitHub, Vercel) |

**Total:** 215 tests across 22 files, **61% coverage**, all green ✅

---

## What's Fixed (vs Original Workflow)

| Problem | Original | ASES |
|---------|----------|------|
| **Credentials** | Invalid `$credentials` expression | Proper env-based injection |
| **Deduplication** | Inverted logic, drops new jobs | PostgreSQL UPSERT, never misses |
| **Tests** | Hardcoded `PASS` every time | Real `npm install && npm test` |
| **Code delivery** | Markdown in Gist | Clean files in GitHub repo |
| **Deploy** | Disconnected from generation | Auto-deploy after tests pass |
| **Scoring** | Single AI call | Weighted: keywords + AI + recency |
| **Proposals** | One-shot | 2-pass with self-critique |
| **CRM** | Hanging webhooks | 202 ACK + async processing |
| **Error handling** | None | Retry, circuit breaker, dead letter |
| **Multi-tenant** | None | Full tenant isolation + billing |
| **Prompt caching** | None | Redis cache, 20–35% token savings |
| **Memory / learning** | None | `code_patterns` table, self-improves each job |
| **HITL safety** | Puppeteer auto-fires | Two-stage inline keyboard approval gate |
| **n8n orchestrator** | Sheets + fake tests | PostgreSQL + real Docker sandbox calls |

---

## Quick Start

```bash
# 1. Clone and configure
git clone <repo>
cd ases
cp .env.example .env
# Edit .env with your keys

# 2. Launch
cd docker
docker compose up -d

# 3. Import n8n workflow
# Visit https://yourdomain.com → Workflows → Import → n8n_orchestrator.json

# 4. Test
curl -X POST https://yourdomain.com/api/dev-task \
  -H "Content-Type: application/json" \
  -d '{"action":"generate_code","task":"Build auth API","tech_stack":"Node.js + Express"}'

# 5. Run TDD gates (validates everything works)
cd .. && run_tdd_gates.bat all
```

---

## File Structure

```
ases/
├── agent_service/          # FastAPI multi-agent engine
│   ├── main.py            # API routes
│   ├── agent_loop.py      # Core: Planner → Coder → Executor → Reviewer
│   ├── parser.py          # FILE: block extraction
│   ├── sandbox.py         # Docker container management
│   ├── tools.py           # Cost calculation, context truncation
│   ├── redis_cache.py     # Prompt cache (SHA-256 key, TTL-aware)
│   ├── models.py          # Pydantic models
│   ├── config.py          # Settings
│   ├── requirements.txt   # Python deps
│   └── Dockerfile         # Container build
├── docker/
│   ├── docker-compose.yml # Full stack orchestration
│   └── nginx.conf         # Reverse proxy + SSL
├── database/
│   └── init.sql           # PostgreSQL schema + indexes
├── tests/
│   ├── test_integration_e2e.py    # 6 E2E tests (ALL externals mocked)
│   ├── test_smoke_gate.py         # 3 smoke tests
│   ├── test_syntax_gate.py        # 3 syntax tests
│   ├── test_main.py               # Route tests
│   └── ... (16 more test files)
├── n8n_orchestrator.json  # Clean n8n workflow (orchestration only)
├── ases_architecture.md   # Full architecture document
├── DEPLOYMENT.md          # Step-by-step production guide
├── TDD_GATES_DOCUMENTATION.md  # Full gate documentation
├── pytest.ini            # Pytest config
├── run_tdd_gates.bat      # Windows gate runner
├── run_tdd_gates.sh       # Unix gate runner
├── .env.example           # Configuration template
└── README.md              # This file
```

---

## The Revolutionary Part

Most "AI coding" tools give you text. ASES gives you **verified, deployed software**.

### The Iteration Loop

```python
for iteration in range(1, 6):
    # 1. Generate code
    files = coder_agent(task, previous_errors)

    # 2. Write to sandbox
    write_files_to_docker(files)

    # 3. Execute tests
    result = run_command("npm install && npm test")

    if result.success:
        # 4. Quality review
        review = reviewer_agent(files, result)
        if review.approved:
            commit_to_github()
            deploy_to_vercel()
            break
        else:
            previous_errors = review.issues
    else:
        previous_errors = result.stderr
```

**Average iterations in testing: 1.3** (most tasks pass on first try)

---

## Cost Optimization

| Agent | Model | Cost per 1K calls |
|-------|-------|-------------------|
| Planner | gpt-4o-mini | ~$0.50 |
| Coder | gpt-4o | ~$8.00 |
| Reviewer | gpt-4o-mini | ~$0.30 |
| **Total per task** | | **~$0.05-0.30** |

---

## Safety

- **Network isolation**: Sandboxes run with `--network none`
- **Resource limits**: 1 CPU, 512MB RAM per sandbox
- **Auto-cleanup**: Sandboxes destroyed after 10 minutes
- **Path sanitization**: Prevents directory traversal
- **Token budget**: Hard stop at 50K tokens per task

---

## CI/CD Pipeline

**GitHub Actions** (`.github/workflows/tdd-gates.yml`):

```yaml
# Triggers: push/PR to main, develop
jobs:
  smoke_gate:      # < 30s
  syntax_gate:     # < 60s
  integration_gate: # < 3min (full pipeline with mocks)
  coverage:        # HTML + XML artifacts
  docker_build:    # main branch only
```

---

## Documentation

- **Full TDD Gates Documentation:** [TDD_GATES_DOCUMENTATION.md](TDD_GATES_DOCUMENTATION.md)
- **Architecture & Patterns:** `AGENTS.md` (workspace root)
- **Deployment Guide:** `DEPLOYMENT.md`
- **Architecture Doc:** `ases_architecture.md`

---

## Requirements

```bash
# Required
OPENAI_API_KEY=sk-...
GITHUB_TOKEN=ghp_...

# Optional
VERCEL_TOKEN=...
TELEGRAM_BOT_TOKEN=...
UPWORK_RSS_URL=...
SENDGRID_API_KEY=...
```

---

## Dev Commands

```bash
# Start dev stack
docker compose -f docker-compose.dev.yml up -d

# View logs
docker compose logs -f agent

# Health check
curl http://localhost:8000/health
# {"status": "healthy", "version": "2.0.0"}

# Submit dev task
curl -X POST http://localhost:8000/dev-task \
  -H "x-tenant-id: default" -H "x-api-key: YOUR_KEY" \
  -d '{"action":"generate_code","task":"Build REST API","tech_stack":"Node.js + Express"}'

# Poll result
curl -H "x-tenant-id: default" -H "x-api-key: YOUR_KEY" \
  http://localhost:8000/jobs/{execution_id}
```

---

## License

MIT — Built for engineers who ship.

---

*This is not automation. This is autonomous engineering.*
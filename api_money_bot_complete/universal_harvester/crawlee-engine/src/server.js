/**
 * HTTP API server — Python orchestrator calls this to run Crawlee jobs.
 * Endpoints:
 *   POST /signup  — single platform signup
 *   POST /batch   — batch signup across multiple platforms
 *   GET  /health  — health check
 *   GET  /sessions — list saved sessions
 */

const express = require('express');
const bodyParser = require('body-parser');
require('dotenv').config();

const { SignupCrawler } = require('./signup-crawler');
const { SessionManager } = require('./session-manager');

const app = express();
app.use(bodyParser.json({ limit: '10mb' }));

const PORT = process.env.PORT || 3001;
const API_KEY = process.env.API_KEY || '';

// Simple API key auth
function authMiddleware(req, res, next) {
  if (!API_KEY) return next();
  const key = req.headers['x-api-key'] || req.query.apiKey;
  if (key !== API_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
}

// ── Health ──────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', engine: 'crawlee-playwright', version: '1.0.0' });
});

// ── Single platform signup ──────────────────────────────────
app.post('/signup', authMiddleware, async (req, res) => {
  const { platform, credentials, mode = 'signup', options = {} } = req.body;
  if (!platform || !credentials) {
    return res.status(400).json({ error: 'Missing platform or credentials' });
  }

  const crawler = new SignupCrawler(options);
  const start = Date.now();

  try {
    const result = await crawler.runPlatform(platform, credentials, mode);
    result.durationMs = Date.now() - start;
    res.json(result);
  } catch (error) {
    res.status(500).json({
      error: error.message,
      stack: process.env.NODE_ENV === 'development' ? error.stack : undefined,
    });
  }
});

// ── Batch signup ────────────────────────────────────────────
app.post('/batch', authMiddleware, async (req, res) => {
  const { jobs, options = {} } = req.body;
  if (!Array.isArray(jobs) || jobs.length === 0) {
    return res.status(400).json({ error: 'Missing jobs array' });
  }

  const crawler = new SignupCrawler(options);
  const start = Date.now();

  try {
    const results = await crawler.runBatch(jobs);
    res.json({
      results,
      totalJobs: jobs.length,
      successful: results.filter(r => r.success).length,
      failed: results.filter(r => !r.success).length,
      durationMs: Date.now() - start,
    });
  } catch (error) {
    res.status(500).json({
      error: error.message,
      stack: process.env.NODE_ENV === 'development' ? error.stack : undefined,
    });
  }
});

// ── List sessions ───────────────────────────────────────────
app.get('/sessions', authMiddleware, async (req, res) => {
  const sm = new SessionManager();
  const sessions = await sm.list();
  res.json({ sessions, count: sessions.length });
});

// ── Delete session ──────────────────────────────────────────
app.delete('/sessions/:platform', authMiddleware, async (req, res) => {
  const sm = new SessionManager();
  await sm.delete(req.params.platform);
  res.json({ deleted: req.params.platform });
});

// ── Start ───────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`[CrawleeEngine] Server running on http://localhost:${PORT}`);
  console.log(`[CrawleeEngine] API Key: ${API_KEY ? 'enabled' : 'disabled'}`);
});

const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');
const { requireOwnedChild } = require('../middleware/ownership');

function extractHostname(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  const trimmed = rawUrl.trim();
  if (!trimmed) return null;
  try {
    const urlString = trimmed.includes('://') ? trimmed : `http://${trimmed}`;
    const parsed = new URL(urlString);
    let host = parsed.hostname.toLowerCase();
    host = host.replace(/^\*?\./, '');
    return host || null;
  } catch (_) {
    return null;
  }
}

function isHostMatch(hostname, sitePattern) {
  if (!hostname || !sitePattern || typeof sitePattern !== 'string') return false;
  const targetHost = hostname.toLowerCase();
  let ruleHost = extractHostname(sitePattern) || sitePattern.toLowerCase().trim();
  ruleHost = ruleHost.replace(/^\*?\./, '');
  if (!ruleHost) return false;
  return targetHost === ruleHost || targetHost.endsWith('.' + ruleHost);
}

router.extractHostname = extractHostname;
router.isHostMatch = isHostMatch;

router.post('/', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const rule = req.body;
    await db.collection('web_filters').doc(rule.id).set(rule);
    res.json({ message: 'Web filter rule saved' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/:childId', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const snapshot = await db.collection('web_filters')
      .where('childId', '==', req.params.childId)
      .where('isActive', '==', true)
      .limit(1)
      .get();

    if (snapshot.empty) return res.json(null);
    res.json(snapshot.docs[0].data());
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/check-url', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const { childId, url } = req.body;
    const hostname = extractHostname(url);
    if (!hostname) {
      return res.status(400).json({ error: 'Invalid URL provided' });
    }

    const snapshot = await db.collection('web_filters')
      .where('childId', '==', childId)
      .where('isActive', '==', true)
      .limit(1)
      .get();

    if (snapshot.empty) return res.json({ blocked: false });

    const rule = snapshot.docs[0].data();
    let blocked = false;
    let reason = null;

    const allowedSites = Array.isArray(rule.allowedSites) ? rule.allowedSites : [];
    const blockedSites = Array.isArray(rule.blockedSites) ? rule.blockedSites : [];

    if (rule.mode === 'allowlist') {
      blocked = !allowedSites.some(site => isHostMatch(hostname, site));
      if (blocked) reason = 'Site not in allowlist';
    } else {
      blocked = blockedSites.some(site => isHostMatch(hostname, site));
      if (blocked) reason = 'Site is blocked';
    }

    res.json({ blocked, reason, mode: rule.mode });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

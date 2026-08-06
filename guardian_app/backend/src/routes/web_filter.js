const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');
const { requireOwnedChild } = require('../middleware/ownership');

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
    const snapshot = await db.collection('web_filters')
      .where('childId', '==', childId)
      .where('isActive', '==', true)
      .limit(1)
      .get();

    if (snapshot.empty) return res.json({ blocked: false });

    const rule = snapshot.docs[0].data();
    let blocked = false;
    let reason = null;

    if (rule.mode === 'allowlist') {
      blocked = !rule.allowedSites.some(site => url.includes(site));
      if (blocked) reason = 'Site not in allowlist';
    } else {
      blocked = rule.blockedSites.some(site => url.includes(site));
      if (blocked) reason = 'Site is blocked';
    }

    res.json({ blocked, reason, mode: rule.mode });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

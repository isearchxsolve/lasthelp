const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');

router.post('/', authenticate, async (req, res) => {
  try {
    const rule = req.body;
    await db.collection('app_rules').doc(rule.id).set(rule);
    res.json({ message: 'App rule saved' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/:childId', authenticate, async (req, res) => {
  try {
    const snapshot = await db.collection('app_rules')
      .where('childId', '==', req.params.childId)
      .orderBy('createdAt', 'desc')
      .get();
    const rules = snapshot.docs.map(doc => doc.data());
    res.json(rules);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.delete('/:ruleId', authenticate, async (req, res) => {
  try {
    await db.collection('app_rules').doc(req.params.ruleId).delete();
    res.json({ message: 'Rule deleted' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/check/:childId/:packageName', authenticate, async (req, res) => {
  try {
    const snapshot = await db.collection('app_rules')
      .where('childId', '==', req.params.childId)
      .where('appPackageName', '==', req.params.packageName)
      .where('isActive', '==', true)
      .limit(1)
      .get();

    if (snapshot.empty) return res.json({ blocked: false });
    const rule = snapshot.docs[0].data();
    res.json({ blocked: rule.ruleType === 'block', rule });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

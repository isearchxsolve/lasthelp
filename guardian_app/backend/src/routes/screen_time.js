const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');

router.post('/rules', authenticate, async (req, res) => {
  try {
    const { childId, dailyLimitMinutes, bedtimeStartHour, bedtimeStartMinute, bedtimeEndHour, bedtimeEndMinute, allowedDays } = req.body;
    const ruleId = `${childId}_screen_time`;

    await db.collection('screen_time').doc(ruleId).set({
      id: ruleId,
      childId,
      parentId: req.userId,
      dailyLimitMinutes,
      bedtimeStartHour,
      bedtimeStartMinute,
      bedtimeEndHour,
      bedtimeEndMinute,
      allowedDays: allowedDays || ['mon','tue','wed','thu','fri','sat','sun'],
      isActive: true,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });

    res.json({ message: 'Rule saved', id: ruleId });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/rules/:childId', authenticate, async (req, res) => {
  try {
    const doc = await db.collection('screen_time').doc(`${req.params.childId}_screen_time`).get();
    if (!doc.exists) return res.json(null);
    res.json(doc.data());
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/records', authenticate, async (req, res) => {
  try {
    const record = req.body;
    await db.collection('screen_time_records').doc(record.id).set(record);
    res.json({ message: 'Record saved' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/records/:childId', authenticate, async (req, res) => {
  try {
    const { from, to } = req.query;
    let query = db.collection('screen_time_records')
      .where('childId', '==', req.params.childId)
      .orderBy('date', 'desc');

    if (from) query = query.where('date', '>=', from);
    if (to) query = query.where('date', '<=', to);

    const snapshot = await query.get();
    const records = snapshot.docs.map(doc => doc.data());
    res.json(records);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');
const { requireOwnedChild } = require('../middleware/ownership');

router.post('/', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const record = req.body;
    await db.collection('locations').doc(record.id).set(record);
    res.json({ message: 'Location recorded' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/:childId', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const { from, to, limit = 100 } = req.query;
    let query = db.collection('locations')
      .where('childId', '==', req.params.childId)
      .orderBy('timestamp', 'desc')
      .limit(parseInt(limit));

    if (from) query = query.where('timestamp', '>=', from);
    if (to) query = query.where('timestamp', '<=', to);

    const snapshot = await query.get();
    const locations = snapshot.docs.map(doc => doc.data());
    res.json(locations);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/latest/:childId', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const snapshot = await db.collection('locations')
      .where('childId', '==', req.params.childId)
      .orderBy('timestamp', 'desc')
      .limit(1)
      .get();

    if (snapshot.empty) return res.json(null);
    res.json(snapshot.docs[0].data());
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/geofences', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const geofence = req.body;
    await db.collection('geofences').doc(geofence.id).set(geofence);
    res.json({ message: 'Geofence saved' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/geofences/:childId', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const snapshot = await db.collection('geofences')
      .where('childId', '==', req.params.childId)
      .get();
    res.json(snapshot.docs.map(doc => doc.data()));
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

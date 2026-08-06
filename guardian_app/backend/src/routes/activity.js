const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');
const { requireOwnedChild, requireOwnParent } = require('../middleware/ownership');

router.post('/', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const activity = req.body;
    await db.collection('activities').doc(activity.id).set(activity);
    res.json({ message: 'Activity recorded' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/:parentId', authenticate, requireOwnParent, async (req, res) => {
  try {
    const { limit = 100, unreadOnly } = req.query;
    let query = db.collection('activities')
      .where('parentId', '==', req.params.parentId)
      .orderBy('timestamp', 'desc')
      .limit(parseInt(limit));

    if (unreadOnly === 'true') query = query.where('isRead', '==', false);

    const snapshot = await query.get();
    const activities = snapshot.docs.map(doc => doc.data());
    res.json(activities);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.patch('/:activityId/read', authenticate, async (req, res) => {
  try {
    await db.collection('activities').doc(req.params.activityId).update({ isRead: true });
    res.json({ message: 'Marked as read' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/mark-all-read', authenticate, requireOwnParent, async (req, res) => {
  try {
    const { parentId } = req.body;
    const snapshot = await db.collection('activities')
      .where('parentId', '==', parentId)
      .where('isRead', '==', false)
      .get();

    const batch = db.batch();
    snapshot.docs.forEach(doc => batch.update(doc.ref, { isRead: true }));
    await batch.commit();

    res.json({ message: 'All marked as read', count: snapshot.size });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

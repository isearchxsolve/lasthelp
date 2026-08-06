const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');

router.get('/', authenticate, async (req, res) => {
  try {
    const snapshot = await db.collection('users')
      .where('parentId', '==', req.userId)
      .where('role', '==', 'child')
      .get();

    const children = snapshot.docs.map(doc => doc.data());
    res.json(children);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/:childId', authenticate, async (req, res) => {
  try {
    const doc = await db.collection('users').doc(req.params.childId).get();
    if (!doc.exists) return res.status(404).json({ error: 'Child not found' });
    const child = doc.data();
    if (child.role !== 'child' || child.parentId !== req.userId) {
      return res.status(404).json({ error: 'Child not found' });
    }
    res.json(child);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.delete('/:childId', authenticate, async (req, res) => {
  try {
    const childRef = db.collection('users').doc(req.params.childId);
    const doc = await childRef.get();
    if (!doc.exists || doc.data().role !== 'child' || doc.data().parentId !== req.userId) {
      return res.status(404).json({ error: 'Child not found' });
    }
    await childRef.update({ parentId: null });
    res.json({ message: 'Child unpaired' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

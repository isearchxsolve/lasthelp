const express = require('express');
const router = express.Router();
const { auth, db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');

router.post('/register', async (req, res) => {
  try {
    const { email, password, name, role, parentId } = req.body;
    const userRecord = await auth.createUser({ email, password, displayName: name });
    const pairingCode = role === 'child' ? generatePairingCode() : null;

    await db.collection('users').doc(userRecord.uid).set({
      id: userRecord.uid,
      email,
      name,
      role,
      parentId: parentId || null,
      pairingCode,
      isPremium: false,
      createdAt: new Date().toISOString(),
      lastActive: new Date().toISOString(),
    });

    res.status(201).json({
      uid: userRecord.uid,
      email,
      name,
      role,
      pairingCode,
    });
  } catch (error) {
    console.error('Register error:', error);
    res.status(400).json({ error: error.message });
  }
});

router.post('/login', async (req, res) => {
  try {
    const { idToken } = req.body;
    const decoded = await auth.verifyIdToken(idToken);
    const doc = await db.collection('users').doc(decoded.uid).get();
    if (!doc.exists) return res.status(404).json({ error: 'User not found' });

    await db.collection('users').doc(decoded.uid).update({
      lastActive: new Date().toISOString(),
    });

    res.json({ user: doc.data() });
  } catch (error) {
    res.status(401).json({ error: error.message });
  }
});

router.get('/profile', authenticate, async (req, res) => {
  try {
    const doc = await db.collection('users').doc(req.userId).get();
    if (!doc.exists) return res.status(404).json({ error: 'User not found' });
    res.json(doc.data());
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/pair', authenticate, async (req, res) => {
  try {
    const { pairingCode } = req.body;
    const snapshot = await db.collection('users')
      .where('pairingCode', '==', pairingCode)
      .where('role', '==', 'child')
      .limit(1)
      .get();

    if (snapshot.empty) return res.status(400).json({ error: 'Invalid pairing code' });

    const childDoc = snapshot.docs[0];
    await db.collection('users').doc(childDoc.id).update({
      parentId: req.userId,
      pairingCode: null,
    });

    res.json({ message: 'Child paired successfully', childId: childDoc.id });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

function generatePairingCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let i = 0; i < 8; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code.substring(0, 4) + '-' + code.substring(4, 8);
}

module.exports = router;

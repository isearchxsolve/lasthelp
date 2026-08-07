const express = require('express');
const router = express.Router();
const { db } = require('../config/firebase');
const { authenticate } = require('../middleware/auth');
const { requireOwnedChild } = require('../middleware/ownership');
const axios = require('axios');

router.post('/config', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const config = req.body;
    await db.collection('content_filter_configs').doc(config.id).set(config);
    res.json({ message: 'Content filter config saved' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/config/:childId', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const snapshot = await db.collection('content_filter_configs')
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

router.post('/analyze-image', authenticate, async (req, res) => {
  try {
    const { imageUrl, sensitivityLevel = 3 } = req.body;
    const apiUrl = process.env.CONTENT_MODERATION_API_URL;
    const apiKey = process.env.CONTENT_MODERATION_API_KEY;

    if (apiUrl && apiKey) {
      const response = await axios.post(apiUrl, {
        image: imageUrl,
        sensitivity: sensitivityLevel,
      }, {
        headers: { 'Authorization': `Bearer ${apiKey}` },
      });
      return res.json(response.data);
    }

    // Fail closed: Flag unmoderated images for review and block by default
    res.json({
      rating: 'flagged',
      status: 'requires_manual_review',
      blocked: true,
      method: 'fallback_fail_closed',
      reason: 'Content moderation service is unconfigured or unavailable',
      confidence: 0.0,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/analyze-text', authenticate, async (req, res) => {
  try {
    const { text, sensitivityLevel = 3, extraKeywords = [] } = req.body;
    const blockedKeywords = [
      'explicit', 'nsfw', 'adult content', 'porn', 'violence', 'gore',
      'hate speech', 'self-harm', 'suicide', 'drugs', 'weapons',
      ...extraKeywords,
    ];

    const lowerText = text.toLowerCase();
    let matchCount = 0;
    const matchedKeywords = [];

    for (const keyword of blockedKeywords) {
      if (lowerText.includes(keyword.toLowerCase())) {
        matchCount++;
        matchedKeywords.push(keyword);
      }
    }

    let rating = 'safe';
    if (matchCount >= 3) rating = 'explicit';
    else if (matchCount >= 2) rating = 'moderate';
    else if (matchCount >= 1) rating = 'suggestive';

    res.json({ rating, matchCount, matchedKeywords, method: 'keyword' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.post('/report-false-positive', authenticate, async (req, res) => {
  try {
    const { contentHash, contentType } = req.body;
    await db.collection('false_positive_reports').add({
      hash: contentHash,
      contentType,
      reportedBy: req.userId,
      reportedAt: new Date().toISOString(),
    });
    res.json({ message: 'Report submitted' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

router.get('/logs/:childId', authenticate, requireOwnedChild, async (req, res) => {
  try {
    const snapshot = await db.collection('blocked_content_logs')
      .where('childId', '==', req.params.childId)
      .orderBy('detectedAt', 'desc')
      .limit(100)
      .get();

    res.json(snapshot.docs.map(doc => doc.data()));
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;

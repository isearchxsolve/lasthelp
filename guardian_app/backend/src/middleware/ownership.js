const { db } = require('../config/firebase');

async function requireOwnedChild(req, res, next) {
  try {
    const childId = req.params.childId || req.body?.childId;
    if (!childId) return res.status(400).json({ error: 'childId is required' });

    const [parentDoc, childDoc] = await Promise.all([
      db.collection('users').doc(req.userId).get(),
      db.collection('users').doc(childId).get(),
    ]);
    if (!parentDoc.exists || parentDoc.data().role !== 'parent' ||
        !childDoc.exists || childDoc.data().role !== 'child' ||
        childDoc.data().parentId !== req.userId) {
      return res.status(404).json({ error: 'Child not found' });
    }
    req.childId = childId;
    next();
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
}

async function requireOwnParent(req, res, next) {
  const parentId = req.params.parentId || req.body?.parentId;
  if (!parentId || parentId !== req.userId) {
    return res.status(404).json({ error: 'Parent not found' });
  }
  next();
}

function requireOwnedDocument(collection, paramName = 'id') {
  return async (req, res, next) => {
    try {
      const doc = await db.collection(collection).doc(req.params[paramName]).get();
      if (!doc.exists || !doc.data().childId) return res.status(404).json({ error: 'Resource not found' });
      req.body = { ...req.body, childId: doc.data().childId };
      return requireOwnedChild(req, res, next);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  };
}

module.exports = { requireOwnedChild, requireOwnParent, requireOwnedDocument };

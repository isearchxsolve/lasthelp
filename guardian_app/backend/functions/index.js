const functions = require('firebase-functions');
const admin = require('firebase-admin');

admin.initializeApp();
const db = admin.firestore();

exports.onNewActivity = functions.firestore
  .document('activities/{activityId}')
  .onCreate(async (snap, context) => {
    const activity = snap.data();
    if (!activity.parentId) return;

    const parentDoc = await db.collection('users').doc(activity.parentId).get();
    const fcmToken = parentDoc.data()?.fcmToken;
    if (!fcmToken) return;

    let title = 'New Activity';
    let body = activity.description || activity.title;

    if (activity.severity === 'high') {
      title = '⚠️ ' + title;
    }

    await admin.messaging().send({
      token: fcmToken,
      notification: { title, body },
      data: { type: activity.type, activityId: activity.id },
    });
  });

exports.onScreenTimeLimitReached = functions.firestore
  .document('screen_time_records/{recordId}')
  .onWrite(async (change, context) => {
    const record = change.after.data();
    if (!record) return;

    const ruleDoc = await db.collection('screen_time').doc(`${record.childId}_screen_time`).get();
    if (!ruleDoc.exists) return;

    const rule = ruleDoc.data();
    if (record.totalMinutes >= rule.dailyLimitMinutes) {
      const childDoc = await db.collection('users').doc(record.childId).get();
      const parentId = childDoc.data()?.parentId;
      if (!parentId) return;

      const parentDoc = await db.collection('users').doc(parentId).get();
      const fcmToken = parentDoc.data()?.fcmToken;
      if (!fcmToken) return;

      await admin.messaging().send({
        token: fcmToken,
        notification: {
          title: 'Screen Time Limit Reached',
          body: `${childDoc.data()?.name || 'Child'} has reached the daily screen time limit`,
        },
        data: { type: 'screen_time_limit', childId: record.childId },
      });
    }
  });

exports.ongeofenceTrigger = functions.firestore
  .document('locations/{locationId}')
  .onCreate(async (snap, context) => {
    const location = snap.data();
    if (!location) return;

    const geofencesSnapshot = await db.collection('geofences')
      .where('childId', '==', location.childId)
      .where('isActive', '==', true)
      .get();

    if (geofencesSnapshot.empty) return;

    const childDoc = await db.collection('users').doc(location.childId).get();
    const parentId = childDoc.data()?.parentId;
    if (!parentId) return;

    const parentDoc = await db.collection('users').doc(parentId).get();
    const fcmToken = parentDoc.data()?.fcmToken;
    if (!fcmToken) return;

    for (const doc of geofencesSnapshot.docs) {
      const geofence = doc.data();
      const distance = calculateDistance(
        location.latitude, location.longitude,
        geofence.latitude, geofence.longitude
      );

      if (distance <= geofence.radiusMeters && geofence.notifyOnEntry) {
        await admin.messaging().send({
          token: fcmToken,
          notification: {
            title: 'Location Alert',
            body: `${childDoc.data()?.name || 'Child'} has entered ${geofence.name}`,
          },
          data: { type: 'geofence_entry', childId: location.childId, geofenceName: geofence.name },
        });
      }
    }
  });

function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function toRad(deg) { return deg * Math.PI / 180; }

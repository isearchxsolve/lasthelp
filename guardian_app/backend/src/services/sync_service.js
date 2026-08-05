const { db } = require('../config/firebase');
const notificationService = require('./notification_service');

class SyncService {
  async syncScreenTime(childId, record) {
    await db.collection('screen_time_records').doc(record.id).set(record);

    const ruleDoc = await db.collection('screen_time').doc(`${childId}_screen_time`).get();
    if (!ruleDoc.exists) return;

    const rule = ruleDoc.data();
    if (record.totalMinutes >= rule.dailyLimitMinutes) {
      const childDoc = await db.collection('users').doc(childId).get();
      const parentId = childDoc.data()?.parentId;
      if (parentId) {
        await notificationService.notifyScreenTimeLimit(childId, parentId, record.totalMinutes, rule.dailyLimitMinutes);
      }
    }
  }

  async syncLocation(childId, locationRecord) {
    await db.collection('locations').doc(locationRecord.id).set(locationRecord);

    const geofencesSnapshot = await db.collection('geofences')
      .where('childId', '==', childId)
      .where('isActive', '==', true)
      .get();

    const childDoc = await db.collection('users').doc(childId).get();
    const parentId = childDoc.data()?.parentId;
    if (!parentId) return;

    for (const geofenceDoc of geofencesSnapshot.docs) {
      const geofence = geofenceDoc.data();
      const distance = this._calculateDistance(
        locationRecord.latitude, locationRecord.longitude,
        geofence.latitude, geofence.longitude
      );

      const wasInside = distance <= geofence.radiusMeters;
      const prevLocation = await this._getPreviousLocation(childId);

      if (prevLocation) {
        const wasInsidePrev = this._calculateDistance(
          prevLocation.latitude, prevLocation.longitude,
          geofence.latitude, geofence.longitude
        ) <= geofence.radiusMeters;

        if (wasInside && !wasInsidePrev && geofence.notifyOnEntry) {
          await notificationService.notifyGeofenceAlert(parentId, childId, geofence.name, 'entry');
        } else if (!wasInside && wasInsidePrev && geofence.notifyOnExit) {
          await notificationService.notifyGeofenceAlert(parentId, childId, geofence.name, 'exit');
        }
      }
    }
  }

  async syncBlockedContent(childId, blockedRecord) {
    await db.collection('blocked_content_logs').doc(blockedRecord.id).set(blockedRecord);

    const childDoc = await db.collection('users').doc(childId).get();
    const parentId = childDoc.data()?.parentId;
    if (parentId) {
      await notificationService.notifyBlockedContent(parentId, childId, blockedRecord.contentType);
    }
  }

  _calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = this._toRad(lat2 - lat1);
    const dLon = this._toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(this._toRad(lat1)) * Math.cos(this._toRad(lat2)) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }

  _toRad(deg) { return deg * Math.PI / 180; }

  async _getPreviousLocation(childId) {
    const snapshot = await db.collection('locations')
      .where('childId', '==', childId)
      .orderBy('timestamp', 'desc')
      .limit(2)
      .get();

    if (snapshot.docs.length < 2) return null;
    return snapshot.docs[1].data();
  }
}

module.exports = new SyncService();

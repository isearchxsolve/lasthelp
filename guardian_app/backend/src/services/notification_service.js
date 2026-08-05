const { messaging, db } = require('../config/firebase');

class NotificationService {
  async sendToDevice(deviceToken, title, body, data = {}) {
    try {
      const message = {
        token: deviceToken,
        notification: { title, body },
        data: { ...data },
        android: {
          priority: 'high',
          notification: {
            channelId: 'guardian_channel',
            priority: 'high',
            sound: 'default',
          },
        },
        apns: {
          payload: {
            aps: {
              sound: 'default',
              badge: 1,
              contentAvailable: true,
            },
          },
        },
      };

      const response = await messaging.send(message);
      return { success: true, messageId: response };
    } catch (error) {
      console.error('Push notification error:', error);
      return { success: false, error: error.message };
    }
  }

  async sendToParent(parentId, title, body, data = {}) {
    try {
      const userDoc = await db.collection('users').doc(parentId).get();
      const fcmToken = userDoc.data()?.fcmToken;
      if (!fcmToken) return { success: false, error: 'No FCM token' };
      return this.sendToDevice(fcmToken, title, body, data);
    } catch (error) {
      console.error('Send to parent error:', error);
      return { success: false, error: error.message };
    }
  }

  async sendToChild(childId, title, body, data = {}) {
    try {
      const userDoc = await db.collection('users').doc(childId).get();
      const fcmToken = userDoc.data()?.fcmToken;
      if (!fcmToken) return { success: false, error: 'No FCM token' };
      return this.sendToDevice(fcmToken, title, body, data);
    } catch (error) {
      console.error('Send to child error:', error);
      return { success: false, error: error.message };
    }
  }

  async notifyScreenTimeLimit(childId, parentId, minutesUsed, limit) {
    await this.sendToParent(parentId, 'Screen Time Alert',
      `Child has used ${minutesUsed} of ${limit} minutes today`,
      { type: 'screen_time', childId, minutesUsed: minutesUsed.toString(), limit: limit.toString() }
    );
    await this.sendToChild(childId, 'Screen Time Limit',
      `You have ${Math.max(0, limit - minutesUsed)} minutes remaining today`,
      { type: 'screen_time_warning', minutesRemaining: Math.max(0, limit - minutesUsed).toString() }
    );
  }

  async notifyGeofenceAlert(parentId, childId, geofenceName, event) {
    await this.sendToParent(parentId, 'Location Alert',
      `Child ${event === 'entry' ? 'entered' : 'left'} ${geofenceName}`,
      { type: 'geofence', childId, geofenceName, event }
    );
  }

  async notifyBlockedContent(parentId, childId, contentType) {
    await this.sendToParent(parentId, 'Content Blocked',
      `Inappropriate ${contentType} was blocked on child's device`,
      { type: 'content_blocked', childId, contentType }
    );
  }
}

module.exports = new NotificationService();

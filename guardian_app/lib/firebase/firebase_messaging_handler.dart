import 'package:firebase_messaging/firebase_messaging.dart';
import '../services/notification_service.dart';

class FirebaseMessagingHandler {
  final NotificationService _notificationService = NotificationService();

  Future<void> initialize() async {
    final messaging = FirebaseMessaging.instance;

    await messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    FirebaseMessaging.onBackgroundMessage(_handleBackgroundMessage);
  }

  void _handleForegroundMessage(RemoteMessage message) {
    final notification = message.notification;
    if (notification != null) {
      _notificationService.showLocalNotification(
        id: message.hashCode,
        title: notification.title ?? '',
        body: notification.body ?? '',
        payload: message.data.toString(),
      );
    }
  }

  void _handleNotificationTap(RemoteMessage message) {
    // Navigate based on notification data
  }
}

@pragma('vm:entry-point')
Future<void> _handleBackgroundMessage(RemoteMessage message) async {
  // Handle background message
}

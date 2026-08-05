import 'package:flutter/foundation.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/activity_model.dart';
import '../core/constants.dart';

class ActivityProvider with ChangeNotifier {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  List<ActivityRecord> _activities = [];
  int _unreadCount = 0;
  bool _isLoading = false;
  String? _error;
  StreamSubscription? _subscription;

  List<ActivityRecord> get activities => _activities;
  int get unreadCount => _unreadCount;
  bool get isLoading => _isLoading;
  String? get error => _error;

  void watch(String parentId) {
    _subscription?.cancel();
    _subscription = _firestore
        .collection(AppConstants.firebaseCollectionActivities)
        .where('parentId', isEqualTo: parentId)
        .orderBy('timestamp', descending: true)
        .limit(100)
        .snapshots()
        .listen((snapshot) {
      _activities = snapshot.docs.map((doc) => ActivityRecord.fromMap(doc.data())).toList();
      _unreadCount = _activities.where((a) => !a.isRead).length;
      notifyListeners();
    });
  }

  Future<void> markAsRead(String activityId) async {
    await _firestore
        .collection(AppConstants.firebaseCollectionActivities)
        .doc(activityId)
        .update({'isRead': true});
  }

  Future<void> markAllAsRead() async {
    final batch = _firestore.batch();
    for (final activity in _activities.where((a) => !a.isRead)) {
      batch.update(
        _firestore.collection(AppConstants.firebaseCollectionActivities).doc(activity.id),
        {'isRead': true},
      );
    }
    await batch.commit();
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}

import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/screen_time_model.dart';
import '../core/constants.dart';

class ScreenTimeService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<void> saveRule(ScreenTimeRule rule) async {
    await _firestore
        .collection(AppConstants.firebaseCollectionScreenTime)
        .doc(rule.id)
        .set(rule.toMap());
  }

  Future<ScreenTimeRule?> getRule(String childId) async {
    final snapshot = await _firestore
        .collection(AppConstants.firebaseCollectionScreenTime)
        .where('childId', isEqualTo: childId)
        .where('isActive', isEqualTo: true)
        .limit(1)
        .get();
    if (snapshot.docs.isEmpty) return null;
    return ScreenTimeRule.fromMap(snapshot.docs.first.data());
  }

  Future<void> recordUsage(ScreenTimeRecord record) async {
    await _firestore
        .collection('screen_time_records')
        .doc(record.id)
        .set({
          ...record.toMap(),
          'serverTimestamp': FieldValue.serverTimestamp(),
        });
  }

  Future<List<ScreenTimeRecord>> getRecords(String childId, {DateTime? from, DateTime? to}) async {
    var query = _firestore
        .collection('screen_time_records')
        .where('childId', isEqualTo: childId)
        .orderBy('date', descending: true);

    if (from != null) query = query.where('date', isGreaterThanOrEqualTo: from.toIso8601String());
    if (to != null) query = query.where('date', isLessThanOrEqualTo: to.toIso8601String());

    final snapshot = await query.get();
    return snapshot.docs.map((doc) => ScreenTimeRecord.fromMap(doc.data())).toList();
  }

  Stream<ScreenTimeRule?> watchRule(String childId) {
    return _firestore
        .collection(AppConstants.firebaseCollectionScreenTime)
        .where('childId', isEqualTo: childId)
        .where('isActive', isEqualTo: true)
        .snapshots()
        .map((snapshot) => snapshot.docs.isEmpty ? null : ScreenTimeRule.fromMap(snapshot.docs.first.data()));
  }
}

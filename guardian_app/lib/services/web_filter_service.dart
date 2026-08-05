import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/web_filter_model.dart';
import '../core/constants.dart';

class WebFilterService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<void> saveRule(WebFilterRule rule) async {
    await _firestore
        .collection(AppConstants.firebaseCollectionWebFilters)
        .doc(rule.id)
        .set(rule.toMap());
  }

  Future<WebFilterRule?> getRule(String childId) async {
    final snapshot = await _firestore
        .collection(AppConstants.firebaseCollectionWebFilters)
        .where('childId', isEqualTo: childId)
        .where('isActive', isEqualTo: true)
        .limit(1)
        .get();
    if (snapshot.docs.isEmpty) return null;
    return WebFilterRule.fromMap(snapshot.docs.first.data());
  }

  Stream<WebFilterRule?> watchRule(String childId) {
    return _firestore
        .collection(AppConstants.firebaseCollectionWebFilters)
        .where('childId', isEqualTo: childId)
        .where('isActive', isEqualTo: true)
        .limit(1)
        .snapshots()
        .map((snapshot) => snapshot.docs.isEmpty ? null : WebFilterRule.fromMap(snapshot.docs.first.data()));
  }

  Future<bool> isSiteBlocked(String childId, String url, {bool isIncognito = false}) async {
    final rule = await getRule(childId);
    if (rule == null) return false;

    if (isIncognito && rule.blockIncognito) return true;

    if (rule.mode == WebFilterMode.allowlist) {
      return !rule.allowedSites.any((site) => url.contains(site));
    }

    if (rule.blockedSites.any((site) => url.contains(site))) return true;
    return false;
  }
}

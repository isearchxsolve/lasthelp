import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/app_rule_model.dart';
import '../core/constants.dart';

class AppBlockService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<void> saveRule(AppRule rule) async {
    await _firestore
        .collection(AppConstants.firebaseCollectionAppRules)
        .doc(rule.id)
        .set(rule.toMap());
  }

  Future<void> deleteRule(String ruleId) async {
    await _firestore
        .collection(AppConstants.firebaseCollectionAppRules)
        .doc(ruleId)
        .delete();
  }

  Future<List<AppRule>> getRules(String childId) async {
    final snapshot = await _firestore
        .collection(AppConstants.firebaseCollectionAppRules)
        .where('childId', isEqualTo: childId)
        .orderBy('createdAt', descending: true)
        .get();
    return snapshot.docs.map((doc) => AppRule.fromMap(doc.data())).toList();
  }

  Stream<List<AppRule>> watchRules(String childId) {
    return _firestore
        .collection(AppConstants.firebaseCollectionAppRules)
        .where('childId', isEqualTo: childId)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map((snapshot) => snapshot.docs.map((doc) => AppRule.fromMap(doc.data())).toList());
  }

  Future<bool> isAppBlocked(String childId, String packageName) async {
    final rules = await getRules(childId);
    for (final rule in rules) {
      if (rule.appPackageName == packageName && rule.isActive) {
        if (rule.ruleType == AppRuleType.block) return true;
        if (rule.ruleType == AppRuleType.allow) return false;
      }
    }
    return false;
  }
}

import 'dart:convert';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:crypto/crypto.dart';
import '../models/content_filter_model.dart';
import '../core/constants.dart';

class ContentFilterService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  static const List<String> _defaultBlockedKeywords = [
    'explicit', 'nsfw', 'adult content', 'porn', 'violence', 'gore',
    'hate speech', 'self-harm', 'suicide', 'drugs', 'weapons',
  ];

  static const List<String> _defaultBlockedPhrases = [
    'how to self harm', 'how to commit suicide', 'buy weapons online',
    'child pornography', 'extremist content',
  ];

  Future<void> saveConfig(ContentFilterConfig config) async {
    await _firestore
        .collection('content_filter_configs')
        .doc(config.id)
        .set(config.toMap());
  }

  Future<ContentFilterConfig?> getConfig(String childId) async {
    final snapshot = await _firestore
        .collection('content_filter_configs')
        .where('childId', isEqualTo: childId)
        .where('isActive', isEqualTo: true)
        .limit(1)
        .get();
    if (snapshot.docs.isEmpty) return null;
    return ContentFilterConfig.fromMap(snapshot.docs.first.data());
  }

  Stream<ContentFilterConfig?> watchConfig(String childId) {
    return _firestore
        .collection('content_filter_configs')
        .where('childId', isEqualTo: childId)
        .where('isActive', isEqualTo: true)
        .limit(1)
        .snapshots()
        .map((snapshot) => snapshot.docs.isEmpty ? null : ContentFilterConfig.fromMap(snapshot.docs.first.data()));
  }

  Future<void> logBlockedContent(BlockedContentRecord record) async {
    await _firestore
        .collection('blocked_content_logs')
        .doc(record.id)
        .set(record.toMap());
  }

  Stream<List<BlockedContentRecord>> watchBlockedLogs(String childId) {
    return _firestore
        .collection('blocked_content_logs')
        .where('childId', isEqualTo: childId)
        .orderBy('detectedAt', descending: true)
        .snapshots()
        .map((snapshot) => snapshot.docs.map((doc) => BlockedContentRecord.fromMap(doc.data())).toList());
  }

  Future<ContentRating> analyzeImage(List<int> imageBytes, {int sensitivityLevel = 3}) async {
    final hash = sha256.convert(imageBytes).toString();
    if (await _isKnownInappropriateHash(hash)) {
      return ContentRating.explicit;
    }
    final sizeKb = imageBytes.length ~/ 1024;
    if (sizeKb > 5120 && sensitivityLevel >= 4) {
      return ContentRating.suggestive;
    }
    return ContentRating.safe;
  }

  Future<ContentRating> analyzeText(String text, {int sensitivityLevel = 3, List<String>? extraKeywords}) async {
    final lowerText = text.toLowerCase();
    final keywords = [
      ..._defaultBlockedKeywords,
      ..._defaultBlockedPhrases,
      ...(extraKeywords ?? []),
    ];

    int matchCount = 0;
    for (final keyword in keywords) {
      if (lowerText.contains(keyword.toLowerCase())) {
        matchCount++;
      }
    }

    if (matchCount == 0) return ContentRating.safe;
    if (matchCount >= 3) return ContentRating.explicit;
    if (matchCount >= 2) return ContentRating.moderate;
    return ContentRating.suggestive;
  }

  Future<bool> shouldHideImage(List<int> imageBytes, ContentFilterConfig config) async {
    if (!config.filterImages) return false;
    final rating = await analyzeImage(imageBytes, sensitivityLevel: config.imageSensitivityLevel);
    return rating.index >= ContentRating.moderate.index;
  }

  Future<bool> shouldBlockText(String text, ContentFilterConfig config) async {
    if (!config.filterText) return false;
    final rating = await analyzeText(text, sensitivityLevel: config.textSensitivityLevel, extraKeywords: config.customBlockedKeywords);
    return rating.index >= ContentRating.moderate.index;
  }

  Future<bool> _isKnownInappropriateHash(String hash) async {
    final snapshot = await _firestore
        .collection('known_content_hashes')
        .where('hash', isEqualTo: hash)
        .where('rating', whereIn: ['explicit', 'dangerous'])
        .limit(1)
        .get();
    return snapshot.docs.isNotEmpty;
  }

  String computeHash(List<int> bytes) {
    return sha256.convert(bytes).toString();
  }

  Future<void> reportFalsePositive(String contentHash, ContentType type) async {
    await _firestore.collection('false_positive_reports').add({
      'hash': contentHash,
      'contentType': type.name,
      'reportedAt': DateTime.now().toIso8601String(),
    });
  }
}

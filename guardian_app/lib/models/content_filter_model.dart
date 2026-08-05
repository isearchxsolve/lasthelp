enum ContentType { image, video, audio, text, appScreen }
enum ContentRating { safe, suggestive, moderate, explicit, dangerous }
enum DetectionMethod { localML, hashMatch, keywordScan, apiCheck, heuristic }

class BlockedContentRecord {
  final String id;
  final String childId;
  final ContentType contentType;
  final String contentHash;
  final String? sourceApp;
  final String? fileName;
  final ContentRating rating;
  final DetectionMethod detectedBy;
  final double confidenceScore;
  final DateTime detectedAt;
  final bool wasHidden;

  BlockedContentRecord({
    required this.id,
    required this.childId,
    required this.contentType,
    required this.contentHash,
    this.sourceApp,
    this.fileName,
    required this.rating,
    required this.detectedBy,
    this.confidenceScore = 0.0,
    required this.detectedAt,
    this.wasHidden = true,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'contentType': contentType.name,
    'contentHash': contentHash,
    'sourceApp': sourceApp,
    'fileName': fileName,
    'rating': rating.name,
    'detectedBy': detectedBy.name,
    'confidenceScore': confidenceScore,
    'detectedAt': detectedAt.toIso8601String(),
    'wasHidden': wasHidden,
  };

  factory BlockedContentRecord.fromMap(Map<String, dynamic> map) => BlockedContentRecord(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    contentType: ContentType.values.firstWhere((e) => e.name == map['contentType']),
    contentHash: map['contentHash'] ?? '',
    sourceApp: map['sourceApp'],
    fileName: map['fileName'],
    rating: ContentRating.values.firstWhere((e) => e.name == (map['rating'] ?? 'explicit')),
    detectedBy: DetectionMethod.values.firstWhere((e) => e.name == (map['detectedBy'] ?? 'heuristic')),
    confidenceScore: (map['confidenceScore'] ?? 0.0).toDouble(),
    detectedAt: DateTime.parse(map['detectedAt'] ?? DateTime.now().toIso8601String()),
    wasHidden: map['wasHidden'] ?? true,
  );
}

class ContentFilterConfig {
  final String id;
  final String childId;
  final String parentId;
  final bool filterImages;
  final bool filterVideos;
  final bool filterAudio;
  final bool filterText;
  final int imageSensitivityLevel;
  final int videoSensitivityLevel;
  final int audioSensitivityLevel;
  final int textSensitivityLevel;
  final List<String> customBlockedKeywords;
  final List<String> customBlockedPhrases;
  final bool blurImages;
  final bool muteAudio;
  final bool hideVideos;
  final bool blockText;
  final bool enableScreenOverlay;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  ContentFilterConfig({
    required this.id,
    required this.childId,
    required this.parentId,
    this.filterImages = true,
    this.filterVideos = true,
    this.filterAudio = true,
    this.filterText = true,
    this.imageSensitivityLevel = 3,
    this.videoSensitivityLevel = 3,
    this.audioSensitivityLevel = 3,
    this.textSensitivityLevel = 3,
    this.customBlockedKeywords = const [],
    this.customBlockedPhrases = const [],
    this.blurImages = true,
    this.muteAudio = true,
    this.hideVideos = true,
    this.blockText = true,
    this.enableScreenOverlay = true,
    this.isActive = true,
    required this.createdAt,
    required this.updatedAt,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'parentId': parentId,
    'filterImages': filterImages,
    'filterVideos': filterVideos,
    'filterAudio': filterAudio,
    'filterText': filterText,
    'imageSensitivityLevel': imageSensitivityLevel,
    'videoSensitivityLevel': videoSensitivityLevel,
    'audioSensitivityLevel': audioSensitivityLevel,
    'textSensitivityLevel': textSensitivityLevel,
    'customBlockedKeywords': customBlockedKeywords,
    'customBlockedPhrases': customBlockedPhrases,
    'blurImages': blurImages,
    'muteAudio': muteAudio,
    'hideVideos': hideVideos,
    'blockText': blockText,
    'enableScreenOverlay': enableScreenOverlay,
    'isActive': isActive,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  );

  factory ContentFilterConfig.fromMap(Map<String, dynamic> map) => ContentFilterConfig(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    parentId: map['parentId'] ?? '',
    filterImages: map['filterImages'] ?? true,
    filterVideos: map['filterVideos'] ?? true,
    filterAudio: map['filterAudio'] ?? true,
    filterText: map['filterText'] ?? true,
    imageSensitivityLevel: map['imageSensitivityLevel'] ?? 3,
    videoSensitivityLevel: map['videoSensitivityLevel'] ?? 3,
    audioSensitivityLevel: map['audioSensitivityLevel'] ?? 3,
    textSensitivityLevel: map['textSensitivityLevel'] ?? 3,
    customBlockedKeywords: List<String>.from(map['customBlockedKeywords'] ?? []),
    customBlockedPhrases: List<String>.from(map['customBlockedPhrases'] ?? []),
    blurImages: map['blurImages'] ?? true,
    muteAudio: map['muteAudio'] ?? true,
    hideVideos: map['hideVideos'] ?? true,
    blockText: map['blockText'] ?? true,
    enableScreenOverlay: map['enableScreenOverlay'] ?? true,
    isActive: map['isActive'] ?? true,
    createdAt: DateTime.parse(map['createdAt'] ?? DateTime.now().toIso8601String()),
    updatedAt: DateTime.parse(map['updatedAt'] ?? DateTime.now().toIso8601String()),
  );
}

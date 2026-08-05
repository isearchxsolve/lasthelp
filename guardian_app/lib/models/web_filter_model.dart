enum WebFilterMode { allowlist, blocklist, smart }
enum ContentCategory { adult, violence, gambling, social, gaming, shopping, streaming, news, educational, other }

class WebFilterRule {
  final String id;
  final String childId;
  final String parentId;
  final WebFilterMode mode;
  final List<String> allowedSites;
  final List<String> blockedSites;
  final List<ContentCategory> blockedCategories;
  final bool blockIncognito;
  final bool safeSearchEnabled;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  WebFilterRule({
    required this.id,
    required this.childId,
    required this.parentId,
    this.mode = WebFilterMode.smart,
    this.allowedSites = const [],
    this.blockedSites = const [],
    this.blockedCategories = const [ContentCategory.adult, ContentCategory.violence, ContentCategory.gambling],
    this.blockIncognito = true,
    this.safeSearchEnabled = true,
    this.isActive = true,
    required this.createdAt,
    required this.updatedAt,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'parentId': parentId,
    'mode': mode.name,
    'allowedSites': allowedSites,
    'blockedSites': blockedSites,
    'blockedCategories': blockedCategories.map((e) => e.name).toList(),
    'blockIncognito': blockIncognito,
    'safeSearchEnabled': safeSearchEnabled,
    'isActive': isActive,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  factory WebFilterRule.fromMap(Map<String, dynamic> map) => WebFilterRule(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    parentId: map['parentId'] ?? '',
    mode: WebFilterMode.values.firstWhere((e) => e.name == (map['mode'] ?? 'smart')),
    allowedSites: List<String>.from(map['allowedSites'] ?? []),
    blockedSites: List<String>.from(map['blockedSites'] ?? []),
    blockedCategories: (map['blockedCategories'] as List?)?.map((e) => ContentCategory.values.firstWhere((c) => c.name == e)).toList() ?? [],
    blockIncognito: map['blockIncognito'] ?? true,
    safeSearchEnabled: map['safeSearchEnabled'] ?? true,
    isActive: map['isActive'] ?? true,
    createdAt: DateTime.parse(map['createdAt'] ?? DateTime.now().toIso8601String()),
    updatedAt: DateTime.parse(map['updatedAt'] ?? DateTime.now().toIso8601String()),
  );
}

enum AppRuleType { allow, block, timeLimit }

class AppRule {
  final String id;
  final String childId;
  final String parentId;
  final String appPackageName;
  final String appName;
  final AppRuleType ruleType;
  final int? dailyLimitMinutes;
  final List<String> allowedDays;
  final int? startHour;
  final int? startMinute;
  final int? endHour;
  final int? endMinute;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  AppRule({
    required this.id,
    required this.childId,
    required this.parentId,
    required this.appPackageName,
    required this.appName,
    required this.ruleType,
    this.dailyLimitMinutes,
    this.allowedDays = const ['mon','tue','wed','thu','fri','sat','sun'],
    this.startHour,
    this.startMinute,
    this.endHour,
    this.endMinute,
    this.isActive = true,
    required this.createdAt,
    required this.updatedAt,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'parentId': parentId,
    'appPackageName': appPackageName,
    'appName': appName,
    'ruleType': ruleType.name,
    'dailyLimitMinutes': dailyLimitMinutes,
    'allowedDays': allowedDays,
    'startHour': startHour,
    'startMinute': startMinute,
    'endHour': endHour,
    'endMinute': endMinute,
    'isActive': isActive,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  factory AppRule.fromMap(Map<String, dynamic> map) => AppRule(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    parentId: map['parentId'] ?? '',
    appPackageName: map['appPackageName'] ?? '',
    appName: map['appName'] ?? '',
    ruleType: AppRuleType.values.firstWhere((e) => e.name == map['ruleType']),
    dailyLimitMinutes: map['dailyLimitMinutes'],
    allowedDays: List<String>.from(map['allowedDays'] ?? ['mon','tue','wed','thu','fri','sat','sun']),
    startHour: map['startHour'],
    startMinute: map['startMinute'],
    endHour: map['endHour'],
    endMinute: map['endMinute'],
    isActive: map['isActive'] ?? true,
    createdAt: DateTime.parse(map['createdAt'] ?? DateTime.now().toIso8601String()),
    updatedAt: DateTime.parse(map['updatedAt'] ?? DateTime.now().toIso8601String()),
  );
}

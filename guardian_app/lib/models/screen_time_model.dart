class ScreenTimeRule {
  final String id;
  final String childId;
  final String parentId;
  final int dailyLimitMinutes;
  final int? bedtimeStartHour;
  final int? bedtimeStartMinute;
  final int? bedtimeEndHour;
  final int? bedtimeEndMinute;
  final List<String> allowedDays;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  ScreenTimeRule({
    required this.id,
    required this.childId,
    required this.parentId,
    required this.dailyLimitMinutes,
    this.bedtimeStartHour,
    this.bedtimeStartMinute,
    this.bedtimeEndHour,
    this.bedtimeEndMinute,
    this.allowedDays = const ['mon','tue','wed','thu','fri','sat','sun'],
    this.isActive = true,
    required this.createdAt,
    required this.updatedAt,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'parentId': parentId,
    'dailyLimitMinutes': dailyLimitMinutes,
    'bedtimeStartHour': bedtimeStartHour,
    'bedtimeStartMinute': bedtimeStartMinute,
    'bedtimeEndHour': bedtimeEndHour,
    'bedtimeEndMinute': bedtimeEndMinute,
    'allowedDays': allowedDays,
    'isActive': isActive,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  factory ScreenTimeRule.fromMap(Map<String, dynamic> map) => ScreenTimeRule(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    parentId: map['parentId'] ?? '',
    dailyLimitMinutes: map['dailyLimitMinutes'] ?? 120,
    bedtimeStartHour: map['bedtimeStartHour'],
    bedtimeStartMinute: map['bedtimeStartMinute'],
    bedtimeEndHour: map['bedtimeEndHour'],
    bedtimeEndMinute: map['bedtimeEndMinute'],
    allowedDays: List<String>.from(map['allowedDays'] ?? ['mon','tue','wed','thu','fri','sat','sun']),
    isActive: map['isActive'] ?? true,
    createdAt: DateTime.parse(map['createdAt'] ?? DateTime.now().toIso8601String()),
    updatedAt: DateTime.parse(map['updatedAt'] ?? DateTime.now().toIso8601String()),
  );
}

class ScreenTimeRecord {
  final String id;
  final String childId;
  final DateTime date;
  final int totalMinutes;
  final Map<String, int> appUsage;
  final int unlockCount;
  final DateTime lastUpdated;

  ScreenTimeRecord({
    required this.id,
    required this.childId,
    required this.date,
    this.totalMinutes = 0,
    this.appUsage = const {},
    this.unlockCount = 0,
    required this.lastUpdated,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'date': date.toIso8601String(),
    'totalMinutes': totalMinutes,
    'appUsage': appUsage,
    'unlockCount': unlockCount,
    'lastUpdated': lastUpdated.toIso8601String(),
  };

  factory ScreenTimeRecord.fromMap(Map<String, dynamic> map) => ScreenTimeRecord(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    date: DateTime.parse(map['date'] ?? DateTime.now().toIso8601String()),
    totalMinutes: map['totalMinutes'] ?? 0,
    appUsage: Map<String, int>.from(map['appUsage'] ?? {}),
    unlockCount: map['unlockCount'] ?? 0,
    lastUpdated: DateTime.parse(map['lastUpdated'] ?? DateTime.now().toIso8601String()),
  );
}

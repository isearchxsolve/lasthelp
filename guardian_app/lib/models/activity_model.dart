enum ActivityType { appUsage, webVisit, screenUnlock, locationChange, ruleBreach, notification }

class ActivityRecord {
  final String id;
  final String childId;
  final String parentId;
  final ActivityType type;
  final String title;
  final String description;
  final Map<String, dynamic>? metadata;
  final String? severity;
  final DateTime timestamp;
  final bool isRead;

  ActivityRecord({
    required this.id,
    required this.childId,
    required this.parentId,
    required this.type,
    required this.title,
    required this.description,
    this.metadata,
    this.severity,
    required this.timestamp,
    this.isRead = false,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'parentId': parentId,
    'type': type.name,
    'title': title,
    'description': description,
    'metadata': metadata,
    'severity': severity,
    'timestamp': timestamp.toIso8601String(),
    'isRead': isRead,
  };

  factory ActivityRecord.fromMap(Map<String, dynamic> map) => ActivityRecord(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    parentId: map['parentId'] ?? '',
    type: ActivityType.values.firstWhere((e) => e.name == map['type']),
    title: map['title'] ?? '',
    description: map['description'] ?? '',
    metadata: map['metadata'] != null ? Map<String, dynamic>.from(map['metadata']) : null,
    severity: map['severity'],
    timestamp: DateTime.parse(map['timestamp'] ?? DateTime.now().toIso8601String()),
    isRead: map['isRead'] ?? false,
  );
}

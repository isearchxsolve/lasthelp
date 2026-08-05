class LocationRecord {
  final String id;
  final String childId;
  final double latitude;
  final double longitude;
  final double? accuracy;
  final double? speed;
  final String? address;
  final DateTime timestamp;

  LocationRecord({
    required this.id,
    required this.childId,
    required this.latitude,
    required this.longitude,
    this.accuracy,
    this.speed,
    this.address,
    required this.timestamp,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'latitude': latitude,
    'longitude': longitude,
    'accuracy': accuracy,
    'speed': speed,
    'address': address,
    'timestamp': timestamp.toIso8601String(),
  };

  factory LocationRecord.fromMap(Map<String, dynamic> map) => LocationRecord(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    latitude: (map['latitude'] ?? 0.0).toDouble(),
    longitude: (map['longitude'] ?? 0.0).toDouble(),
    accuracy: map['accuracy']?.toDouble(),
    speed: map['speed']?.toDouble(),
    address: map['address'],
    timestamp: DateTime.parse(map['timestamp'] ?? DateTime.now().toIso8601String()),
  );
}

class Geofence {
  final String id;
  final String childId;
  final String parentId;
  final String name;
  final double latitude;
  final double longitude;
  final double radiusMeters;
  final bool isActive;
  final bool notifyOnEntry;
  final bool notifyOnExit;
  final DateTime createdAt;

  Geofence({
    required this.id,
    required this.childId,
    required this.parentId,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.radiusMeters,
    this.isActive = true,
    this.notifyOnEntry = true,
    this.notifyOnExit = true,
    required this.createdAt,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'childId': childId,
    'parentId': parentId,
    'name': name,
    'latitude': latitude,
    'longitude': longitude,
    'radiusMeters': radiusMeters,
    'isActive': isActive,
    'notifyOnEntry': notifyOnEntry,
    'notifyOnExit': notifyOnExit,
    'createdAt': createdAt.toIso8601String(),
  };

  factory Geofence.fromMap(Map<String, dynamic> map) => Geofence(
    id: map['id'] ?? '',
    childId: map['childId'] ?? '',
    parentId: map['parentId'] ?? '',
    name: map['name'] ?? '',
    latitude: (map['latitude'] ?? 0.0).toDouble(),
    longitude: (map['longitude'] ?? 0.0).toDouble(),
    radiusMeters: (map['radiusMeters'] ?? 100.0).toDouble(),
    isActive: map['isActive'] ?? true,
    notifyOnEntry: map['notifyOnEntry'] ?? true,
    notifyOnExit: map['notifyOnExit'] ?? true,
    createdAt: DateTime.parse(map['createdAt'] ?? DateTime.now().toIso8601String()),
  );
}

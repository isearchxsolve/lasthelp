enum UserRole { parent, child }

class UserModel {
  final String id;
  final String email;
  final String name;
  final UserRole role;
  final String? parentId;
  final String? pairingCode;
  final bool isPremium;
  final DateTime createdAt;
  final DateTime? lastActive;

  UserModel({
    required this.id,
    required this.email,
    required this.name,
    required this.role,
    this.parentId,
    this.pairingCode,
    this.isPremium = false,
    required this.createdAt,
    this.lastActive,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'email': email,
    'name': name,
    'role': role.name,
    'parentId': parentId,
    'pairingCode': pairingCode,
    'isPremium': isPremium,
    'createdAt': createdAt.toIso8601String(),
    'lastActive': lastActive?.toIso8601String(),
  };

  factory UserModel.fromMap(Map<String, dynamic> map) => UserModel(
    id: map['id'] ?? '',
    email: map['email'] ?? '',
    name: map['name'] ?? '',
    role: map['role'] == 'child' ? UserRole.child : UserRole.parent,
    parentId: map['parentId'],
    pairingCode: map['pairingCode'],
    isPremium: map['isPremium'] ?? false,
    createdAt: DateTime.parse(map['createdAt'] ?? DateTime.now().toIso8601String()),
    lastActive: map['lastActive'] != null ? DateTime.parse(map['lastActive']) : null,
  );
}

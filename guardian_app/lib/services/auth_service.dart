import 'dart:math';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import '../models/user_model.dart';
import '../core/constants.dart';

class AuthService {
  final FirebaseAuth _auth = FirebaseAuth.instance;
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Stream<User?> get authStateChanges => _auth.authStateChanges();
  User? get currentUser => _auth.currentUser;

  Future<UserModel> signUp({
    required String email,
    required String password,
    required String name,
    required UserRole role,
    String? parentId,
  }) async {
    final credential = await _auth.createUserWithEmailAndPassword(
      email: email,
      password: password,
    );
    final user = credential.user!;
    final pairingCode = role == UserRole.child ? _generatePairingCode() : null;

    final userModel = UserModel(
      id: user.uid,
      email: email,
      name: name,
      role: role,
      parentId: parentId,
      pairingCode: pairingCode,
      createdAt: DateTime.now(),
    );

    await _firestore.collection(AppConstants.firebaseCollectionUsers)
        .doc(user.uid).set(userModel.toMap());

    return userModel;
  }

  Future<UserModel> signIn(String email, String password) async {
    final credential = await _auth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
    final doc = await _firestore.collection(AppConstants.firebaseCollectionUsers)
        .doc(credential.user!.uid).get();
    return UserModel.fromMap(doc.data()!);
  }

  Future<void> signOut() => _auth.signOut();

  Future<UserModel> getCurrentUser() async {
    final uid = _auth.currentUser?.uid;
    if (uid == null) throw Exception('Not authenticated');
    final doc = await _firestore.collection(AppConstants.firebaseCollectionUsers)
        .doc(uid).get();
    return UserModel.fromMap(doc.data()!);
  }

  Future<void> pairChild(String pairingCode, String parentId) async {
    final snapshot = await _firestore
        .collection(AppConstants.firebaseCollectionUsers)
        .where('pairingCode', isEqualTo: pairingCode)
        .where('role', isEqualTo: 'child')
        .get();

    if (snapshot.docs.isEmpty) {
      throw Exception('Invalid pairing code');
    }

    final childDoc = snapshot.docs.first;
    await _firestore.collection(AppConstants.firebaseCollectionUsers)
        .doc(childDoc.id).update({'parentId': parentId, 'pairingCode': null});
  }

  Future<List<UserModel>> getChildren(String parentId) async {
    final snapshot = await _firestore
        .collection(AppConstants.firebaseCollectionUsers)
        .where('parentId', isEqualTo: parentId)
        .where('role', isEqualTo: 'child')
        .get();
    return snapshot.docs.map((doc) => UserModel.fromMap(doc.data())).toList();
  }

  String _generatePairingCode() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    final random = Random.secure();
    final code = List.generate(8, (_) => chars[random.nextInt(chars.length)]).join();
    return code.substring(0, 4) + '-' + code.substring(4, 8);
  }
}

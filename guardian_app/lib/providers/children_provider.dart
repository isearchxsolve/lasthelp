import 'package:flutter/foundation.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/user_model.dart';
import '../core/constants.dart';

class ChildrenProvider with ChangeNotifier {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  List<UserModel> _children = [];
  bool _isLoading = false;
  String? _error;
  StreamSubscription? _subscription;

  List<UserModel> get children => _children;
  bool get isLoading => _isLoading;
  String? get error => _error;

  void watchChildren(String parentId) {
    _subscription?.cancel();
    _subscription = _firestore
        .collection(AppConstants.firebaseCollectionUsers)
        .where('parentId', isEqualTo: parentId)
        .where('role', isEqualTo: 'child')
        .snapshots()
        .listen((snapshot) {
      _children = snapshot.docs.map((doc) => UserModel.fromMap(doc.data())).toList();
      notifyListeners();
    });
  }

  Future<void> removeChild(String childId) async {
    await _firestore.collection(AppConstants.firebaseCollectionUsers)
        .doc(childId)
        .update({'parentId': null});
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}

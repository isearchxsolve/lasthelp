import 'package:flutter/foundation.dart';
import '../models/app_rule_model.dart';
import '../services/app_block_service.dart';

class AppRulesProvider with ChangeNotifier {
  final AppBlockService _service = AppBlockService();

  List<AppRule> _rules = [];
  bool _isLoading = false;
  String? _error;
  StreamSubscription? _subscription;

  List<AppRule> get rules => _rules;
  bool get isLoading => _isLoading;
  String? get error => _error;

  void watch(String childId) {
    _subscription?.cancel();
    _subscription = _service.watchRules(childId).listen((rules) {
      _rules = rules;
      notifyListeners();
    });
  }

  Future<void> addRule(AppRule rule) async {
    _isLoading = true;
    notifyListeners();
    try {
      await _service.saveRule(rule);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateRule(AppRule rule) async {
    try {
      await _service.saveRule(rule);
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    }
  }

  Future<void> deleteRule(String ruleId) async {
    try {
      await _service.deleteRule(ruleId);
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}

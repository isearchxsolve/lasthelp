import 'package:flutter/foundation.dart';
import '../models/web_filter_model.dart';
import '../services/web_filter_service.dart';

class WebFilterProvider with ChangeNotifier {
  final WebFilterService _service = WebFilterService();

  WebFilterRule? _rule;
  bool _isLoading = false;
  String? _error;
  StreamSubscription? _subscription;

  WebFilterRule? get rule => _rule;
  bool get isLoading => _isLoading;
  String? get error => _error;

  void watch(String childId) {
    _subscription?.cancel();
    _subscription = _service.watchRule(childId).listen((rule) {
      _rule = rule;
      notifyListeners();
    });
  }

  Future<void> saveRule(WebFilterRule rule) async {
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

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}

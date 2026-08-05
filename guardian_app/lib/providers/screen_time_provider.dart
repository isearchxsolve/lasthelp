import 'package:flutter/foundation.dart';
import '../models/screen_time_model.dart';
import '../services/screen_time_service.dart';
import '../services/content_filter_service.dart';
import '../models/content_filter_model.dart';

class ScreenTimeProvider with ChangeNotifier {
  final ScreenTimeService _service = ScreenTimeService();
  final ContentFilterService _contentFilterService = ContentFilterService();

  ScreenTimeRule? _rule;
  List<ScreenTimeRecord> _records = [];
  ContentFilterConfig? _filterConfig;
  bool _isLoading = false;
  String? _error;
  StreamSubscription? _ruleSubscription;
  StreamSubscription? _configSubscription;

  ScreenTimeRule? get rule => _rule;
  List<ScreenTimeRecord> get records => _records;
  ContentFilterConfig? get filterConfig => _filterConfig;
  bool get isLoading => _isLoading;
  String? get error => _error;

  void watch(String childId) {
    _ruleSubscription = _service.watchRule(childId).listen((rule) {
      _rule = rule;
      notifyListeners();
    });
    _configSubscription = _contentFilterService.watchConfig(childId).listen((config) {
      _filterConfig = config;
      notifyListeners();
    });
  }

  Future<void> saveRule(ScreenTimeRule rule) async {
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

  Future<void> loadRecords(String childId, {DateTime? from, DateTime? to}) async {
    _isLoading = true;
    notifyListeners();
    try {
      _records = await _service.getRecords(childId, from: from, to: to);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> saveFilterConfig(ContentFilterConfig config) async {
    try {
      await _contentFilterService.saveConfig(config);
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _ruleSubscription?.cancel();
    _configSubscription?.cancel();
    super.dispose();
  }
}

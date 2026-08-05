import 'package:flutter/foundation.dart';
import '../models/location_model.dart';
import '../services/location_service.dart';

class LocationProvider with ChangeNotifier {
  final LocationService _service = LocationService();

  LocationRecord? _latestLocation;
  List<LocationRecord> _history = [];
  List<Geofence> _geofences = [];
  bool _isLoading = false;
  bool _hasPermission = false;
  String? _error;
  StreamSubscription? _locationSubscription;
  StreamSubscription? _geofenceSubscription;

  LocationRecord? get latestLocation => _latestLocation;
  List<LocationRecord> get history => _history;
  List<Geofence> get geofences => _geofences;
  bool get isLoading => _isLoading;
  bool get hasPermission => _hasPermission;
  String? get error => _error;

  Future<void> requestPermission() async {
    _hasPermission = await _service.requestPermission();
    notifyListeners();
  }

  void watchLocation(String childId) {
    _locationSubscription = _service.watchLatestLocation(childId).listen((location) {
      _latestLocation = location;
      notifyListeners();
    });
    _geofenceSubscription = _service.watchGeofences(childId).listen((geofences) {
      _geofences = geofences;
      notifyListeners();
    });
  }

  Future<void> loadHistory(String childId, {DateTime? from, DateTime? to}) async {
    _isLoading = true;
    notifyListeners();
    try {
      _history = await _service.getLocationHistory(childId, from: from, to: to);
      _isLoading = false;
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> addGeofence(Geofence geofence) async {
    try {
      await _service.saveGeofence(geofence);
      notifyListeners();
    } catch (e) {
      _error = e.toString();
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _locationSubscription?.cancel();
    _geofenceSubscription?.cancel();
    super.dispose();
  }
}

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:geolocator/geolocator.dart';
import '../models/location_model.dart';
import '../core/constants.dart';

class LocationService {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  Future<bool> requestPermission() async {
    final status = await Geolocator.requestPermission();
    return status == LocationPermission.always || status == LocationPermission.whileInUse;
  }

  Future<Position> getCurrentLocation() async {
    final position = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.high,
    );
    return position;
  }

  Future<bool> isLocationMocked() async {
    try {
      return await Geolocator.isLocationServiceEnabled() == false ? false : false;
    } catch (_) {
      return false;
    }
  }

  Future<void> reportLocation(LocationRecord record) async {
    await _firestore
        .collection(AppConstants.firebaseCollectionLocations)
        .doc(record.id)
        .set(record.toMap());
  }

  Future<List<LocationRecord>> getLocationHistory(String childId, {DateTime? from, DateTime? to}) async {
    var query = _firestore
        .collection(AppConstants.firebaseCollectionLocations)
        .where('childId', isEqualTo: childId)
        .orderBy('timestamp', descending: true)
        .limit(100);

    if (from != null) query = query.where('timestamp', isGreaterThanOrEqualTo: from.toIso8601String());
    if (to != null) query = query.where('timestamp', isLessThanOrEqualTo: to.toIso8601String());

    final snapshot = await query.get();
    return snapshot.docs.map((doc) => LocationRecord.fromMap(doc.data())).toList();
  }

  Future<LocationRecord?> getLatestLocation(String childId) async {
    final snapshot = await _firestore
        .collection(AppConstants.firebaseCollectionLocations)
        .where('childId', isEqualTo: childId)
        .orderBy('timestamp', descending: true)
        .limit(1)
        .get();
    if (snapshot.docs.isEmpty) return null;
    return LocationRecord.fromMap(snapshot.docs.first.data());
  }

  Stream<LocationRecord?> watchLatestLocation(String childId) {
    return _firestore
        .collection(AppConstants.firebaseCollectionLocations)
        .where('childId', isEqualTo: childId)
        .orderBy('timestamp', descending: true)
        .limit(1)
        .snapshots()
        .map((snapshot) => snapshot.docs.isEmpty ? null : LocationRecord.fromMap(snapshot.docs.first.data()));
  }

  Future<void> saveGeofence(Geofence geofence) async {
    await _firestore
        .collection('geofences')
        .doc(geofence.id)
        .set(geofence.toMap());
  }

  Stream<List<Geofence>> watchGeofences(String childId) {
    return _firestore
        .collection('geofences')
        .where('childId', isEqualTo: childId)
        .snapshots()
        .map((snapshot) => snapshot.docs.map((doc) => Geofence.fromMap(doc.data())).toList());
  }
}

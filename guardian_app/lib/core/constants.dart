class AppConstants {
  static const String appName = 'Guardian';
  static const String appVersion = '1.0.0';

  static const Duration syncInterval = Duration(minutes: 5);
  static const Duration locationUpdateInterval = Duration(minutes: 2);
  static const int maxChildrenPerParent = 10;
  static const int maxScreenTimeHours = 24;
  static const double maxLocationRadiusKm = 100.0;

  static const String apiBaseUrl = 'http://localhost:3000/api';
  static const String firebaseCollectionUsers = 'users';
  static const String firebaseCollectionChildren = 'children';
  static const String firebaseCollectionScreenTime = 'screen_time';
  static const String firebaseCollectionAppRules = 'app_rules';
  static const String firebaseCollectionLocations = 'locations';
  static const String firebaseCollectionActivities = 'activities';
  static const String firebaseCollectionWebFilters = 'web_filters';
}

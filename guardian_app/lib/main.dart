import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase/firebase_options.dart';
import 'app.dart';
import 'providers/auth_provider.dart';
import 'providers/children_provider.dart';
import 'providers/screen_time_provider.dart';
import 'providers/app_rules_provider.dart';
import 'providers/location_provider.dart';
import 'providers/activity_provider.dart';
import 'providers/web_filter_provider.dart';
import 'services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  await NotificationService().initialize();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => ChildrenProvider()),
        ChangeNotifierProvider(create: (_) => ScreenTimeProvider()),
        ChangeNotifierProvider(create: (_) => AppRulesProvider()),
        ChangeNotifierProvider(create: (_) => LocationProvider()),
        ChangeNotifierProvider(create: (_) => ActivityProvider()),
        ChangeNotifierProvider(create: (_) => WebFilterProvider()),
      ],
      child: const GuardianApp(),
    ),
  );
}

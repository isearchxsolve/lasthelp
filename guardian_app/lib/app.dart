import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/theme.dart';
import 'core/routes.dart';
import 'providers/auth_provider.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/register_screen.dart';
import 'screens/auth/pairing_screen.dart';
import 'screens/parent/dashboard_screen.dart';
import 'screens/parent/children_list_screen.dart';
import 'screens/parent/child_detail_screen.dart';
import 'screens/parent/screen_time_screen.dart';
import 'screens/parent/app_rules_screen.dart';
import 'screens/parent/web_filter_screen.dart';
import 'screens/parent/location_screen.dart';
import 'screens/parent/activity_reports_screen.dart';
import 'screens/child/child_home_screen.dart';
import 'screens/child/restricted_screen.dart';

class GuardianApp extends StatelessWidget {
  const GuardianApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Guardian',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.light,
      initialRoute: AppRoutes.splash,
      onGenerateRoute: (settings) {
        switch (settings.name) {
          case AppRoutes.login:
            return MaterialPageRoute(builder: (_) => const LoginScreen());
          case AppRoutes.register:
            return MaterialPageRoute(builder: (_) => const RegisterScreen());
          case AppRoutes.pairing:
            return MaterialPageRoute(builder: (_) => const PairingScreen());
          case AppRoutes.parentDashboard:
            return MaterialPageRoute(builder: (_) => const DashboardScreen());
          case AppRoutes.parentChildren:
            return MaterialPageRoute(builder: (_) => const ChildrenListScreen());
          case AppRoutes.parentChildDetail:
            final childId = settings.arguments as String;
            return MaterialPageRoute(builder: (_) => ChildDetailScreen(childId: childId));
          case AppRoutes.parentScreenTime:
            final childId = settings.arguments as String;
            return MaterialPageRoute(builder: (_) => ScreenTimeScreen(childId: childId));
          case AppRoutes.parentAppRules:
            final childId = settings.arguments as String;
            return MaterialPageRoute(builder: (_) => AppRulesScreen(childId: childId));
          case AppRoutes.parentWebFilter:
            final childId = settings.arguments as String;
            return MaterialPageRoute(builder: (_) => WebFilterScreen(childId: childId));
          case AppRoutes.parentLocation:
            final childId = settings.arguments as String;
            return MaterialPageRoute(builder: (_) => LocationScreen(childId: childId));
          case AppRoutes.parentActivityReports:
            final childId = settings.arguments as String;
            return MaterialPageRoute(builder: (_) => ActivityReportsScreen(childId: childId));
          case AppRoutes.childHome:
            return MaterialPageRoute(builder: (_) => const ChildHomeScreen());
          case AppRoutes.childRestricted:
            return MaterialPageRoute(builder: (_) => const RestrictedScreen());
          case AppRoutes.splash:
          default:
            return MaterialPageRoute(builder: (_) => const SplashScreen());
        }
      },
    );
  }
}

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    await Future.delayed(const Duration(seconds: 2));
    if (!mounted) return;
    final auth = context.read<AuthProvider>();
    if (auth.isAuthenticated) {
      Navigator.pushReplacementNamed(
        context,
        auth.isParent ? AppRoutes.parentDashboard : AppRoutes.childHome,
      );
    } else {
      Navigator.pushReplacementNamed(context, AppRoutes.login);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.shield, size: 80, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 16),
            Text('Guardian', style: Theme.of(context).textTheme.headlineLarge?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text('Parental Control', style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Colors.grey)),
            const SizedBox(height: 32),
            const CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}

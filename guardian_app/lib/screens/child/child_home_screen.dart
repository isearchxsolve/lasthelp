import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';
import '../../core/theme.dart';
import '../../core/routes.dart';

class ChildHomeScreen extends StatelessWidget {
  const ChildHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Guardian'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () {
              auth.signOut();
              Navigator.pushReplacementNamed(context, AppRoutes.login);
            },
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.shield, size: 80, color: AppTheme.primaryColor),
              const SizedBox(height: 24),
              Text('Hi ${auth.user?.name ?? 'there'}!', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text('Your device is being monitored', style: const TextStyle(color: Colors.grey)),
              const SizedBox(height: 32),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    children: [
                      Icon(Icons.check_circle, color: Colors.green, size: 48),
                      const SizedBox(height: 16),
                      Text('Your device is paired with your parent\'s account.', textAlign: TextAlign.center, style: TextStyle(color: Colors.grey[600])),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

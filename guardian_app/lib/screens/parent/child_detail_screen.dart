import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/children_provider.dart';
import '../../core/theme.dart';
import '../../core/routes.dart';

class ChildDetailScreen extends StatelessWidget {
  final String childId;
  const ChildDetailScreen({super.key, required this.childId});

  @override
  Widget build(BuildContext context) {
    final children = context.watch<ChildrenProvider>().children;
    final child = children.firstWhere((c) => c.id == childId, orElse: () => children.first);

    final features = [
      _FeatureItem(icon: Icons.timer, title: 'Screen Time', subtitle: 'Set daily limits & bedtime', route: AppRoutes.parentScreenTime, color: const Color(0xFF4A6CF7)),
      _FeatureItem(icon: Icons.apps, title: 'App Rules', subtitle: 'Block or allow apps', route: AppRoutes.parentAppRules, color: const Color(0xFF6C63FF)),
      _FeatureItem(icon: Icons.public, title: 'Web Filter', subtitle: 'Content & site filtering', route: AppRoutes.parentWebFilter, color: const Color(0xFF00D2FF)),
      _FeatureItem(icon: Icons.location_on, title: 'Location', subtitle: 'Real-time tracking & geofences', route: AppRoutes.parentLocation, color: const Color(0xFF2ECC71)),
      _FeatureItem(icon: Icons.analytics, title: 'Activity Reports', subtitle: 'Usage analytics & history', route: AppRoutes.parentActivityReports, color: const Color(0xFFF39C12)),
    ];

    return Scaffold(
      appBar: AppBar(title: Text(child.name)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 32,
                    backgroundColor: AppTheme.primaryColor.withValues(alpha: 0.1),
                    child: Icon(Icons.person, size: 32, color: AppTheme.primaryColor),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(child.name, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 4),
                        Text(child.deviceModel, style: const TextStyle(color: Colors.grey)),
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            Container(
                              width: 8, height: 8,
                              decoration: BoxDecoration(
                                color: child.isOnline ? Colors.green : Colors.grey,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(child.isOnline ? 'Online' : 'Offline', style: TextStyle(color: child.isOnline ? Colors.green : Colors.grey)),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          ...features.map((f) => _FeatureCard(feature: f, childId: childId)),
        ],
      ),
    );
  }
}

class _FeatureItem {
  final IconData icon;
  final String title;
  final String subtitle;
  final String route;
  final Color color;
  _FeatureItem({required this.icon, required this.title, required this.subtitle, required this.route, required this.color});
}

class _FeatureCard extends StatelessWidget {
  final _FeatureItem feature;
  final String childId;
  const _FeatureCard({required this.feature, required this.childId});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: feature.color.withValues(alpha: 0.1),
          child: Icon(feature.icon, color: feature.color),
        ),
        title: Text(feature.title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(feature.subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => Navigator.pushNamed(context, feature.route, arguments: childId),
      ),
    );
  }
}

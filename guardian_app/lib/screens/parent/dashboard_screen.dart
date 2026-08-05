import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';
import '../../providers/children_provider.dart';
import '../../providers/activity_provider.dart';
import '../../core/routes.dart';
import '../../models/user_model.dart';
import '../../models/activity_model.dart';
import '../../widgets/dashboard/stat_card.dart';
import '../../widgets/child/child_card.dart';
import '../../widgets/common/loading_widget.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    final auth = context.read<AuthProvider>();
    if (auth.user != null) {
      context.read<ChildrenProvider>().watchChildren(auth.user!.id);
      context.read<ActivityProvider>().watch(auth.user!.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final childrenProvider = context.watch<ChildrenProvider>();
    final activityProvider = context.watch<ActivityProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Guardian'),
        actions: [
          Stack(
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_outlined),
                onPressed: () {},
              ),
              if (activityProvider.unreadCount > 0)
                Positioned(
                  right: 6, top: 6,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(color: Colors.red, shape: BoxShape.circle),
                    child: Text('${activityProvider.unreadCount}', style: const TextStyle(color: Colors.white, fontSize: 10)),
                  ),
                ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () {
              auth.signOut();
              Navigator.pushReplacementNamed(context, AppRoutes.login);
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {},
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Welcome, ${auth.user?.name ?? 'Parent'}', style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text('${childrenProvider.children.length} child${childrenProvider.children.length == 1 ? '' : 'ren'} connected', style: const TextStyle(color: Colors.grey)),
              const SizedBox(height: 24),
              SizedBox(
                height: 100,
                child: Row(
                  children: [
                    Expanded(child: StatCard(title: 'Screen Time', value: '${_getTodayScreenTime(activityProvider)}m', icon: Icons.timer, color: Colors.blue)),
                    const SizedBox(width: 12),
                    Expanded(child: StatCard(title: 'Alerts', value: '${activityProvider.unreadCount}', icon: Icons.warning, color: Colors.orange)),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Your Children', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
                  TextButton(
                    onPressed: () => Navigator.pushNamed(context, AppRoutes.parentChildren),
                    child: const Text('View All'),
                  ),
                ],
              ),
              if (childrenProvider.children.isEmpty)
                _EmptyChildrenWidget()
              else
                ...childrenProvider.children.map((child) => ChildCard(
                  child: child,
                  onTap: () => Navigator.pushNamed(context, AppRoutes.parentChildDetail, arguments: child.id),
                )),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => Navigator.pushNamed(context, AppRoutes.pairing),
                  icon: const Icon(Icons.add),
                  label: const Text('Add Child Device'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  int _getTodayScreenTime(ActivityProvider provider) {
    final today = DateTime.now();
    final todayActivities = provider.activities.where((a) =>
      a.timestamp.year == today.year &&
      a.timestamp.month == today.month &&
      a.timestamp.day == today.day
    );
    if (todayActivities.isEmpty) return 0;
    final screenTimeActivities = todayActivities.where((a) => a.type == ActivityType.appUsage).toList();
    if (screenTimeActivities.isEmpty) return todayActivities.length * 2;
    return screenTimeActivities.length * 5;
  }
}

class _EmptyChildrenWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          children: [
            Icon(Icons.child_care, size: 48, color: Colors.grey[400]),
            const SizedBox(height: 16),
            Text('No children connected yet', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('Add your child\'s device using the pairing code', style: TextStyle(color: Colors.grey[600])),
          ],
        ),
      ),
    );
  }
}

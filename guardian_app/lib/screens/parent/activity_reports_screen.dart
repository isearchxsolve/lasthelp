import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../../providers/activity_provider.dart';
import '../../models/activity_model.dart';
import '../../widgets/common/loading_widget.dart';

class ActivityReportsScreen extends StatefulWidget {
  final String childId;
  const ActivityReportsScreen({super.key, required this.childId});

  @override
  State<ActivityReportsScreen> createState() => _ActivityReportsScreenState();
}

class _ActivityReportsScreenState extends State<ActivityReportsScreen> {
  String _filter = 'all';

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ActivityProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Activity Reports'),
        actions: [
          if (provider.unreadCount > 0)
            TextButton(
              onPressed: () => provider.markAllAsRead(),
              child: const Text('Mark All Read'),
            ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FilterChip(label: 'All', selected: _filter == 'all', onTap: () => setState(() => _filter = 'all')),
                  _FilterChip(label: 'Screen Time', selected: _filter == 'screen', onTap: () => setState(() => _filter = 'screen')),
                  _FilterChip(label: 'Apps', selected: _filter == 'apps', onTap: () => setState(() => _filter = 'apps')),
                  _FilterChip(label: 'Web', selected: _filter == 'web', onTap: () => setState(() => _filter = 'web')),
                  _FilterChip(label: 'Location', selected: _filter == 'location', onTap: () => setState(() => _filter = 'location')),
                ],
              ),
            ),
          ),
          Expanded(
            child: provider.activities.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.inbox, size: 64, color: Colors.grey[400]),
                      const SizedBox(height: 16),
                      const Text('No activity yet'),
                    ],
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  itemCount: provider.activities.length,
                  itemBuilder: (context, index) {
                    final activity = provider.activities[index];
                    return _ActivityCard(activity: activity, onTap: () => provider.markAsRead(activity.id));
                  },
                ),
          ),
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _FilterChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ChoiceChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) => onTap(),
      ),
    );
  }
}

class _ActivityCard extends StatelessWidget {
  final ActivityRecord activity;
  final VoidCallback onTap;
  const _ActivityCard({required this.activity, required this.onTap});

  IconData get _icon {
    switch (activity.type) {
      case ActivityType.appUsage: return Icons.apps;
      case ActivityType.webVisit: return Icons.public;
      case ActivityType.screenUnlock: return Icons.screen_lock_landscape;
      case ActivityType.locationChange: return Icons.location_on;
      case ActivityType.ruleBreach: return Icons.warning;
      case ActivityType.notification: return Icons.notifications;
    }
  }

  Color get _color {
    switch (activity.severity) {
      case 'high': return Colors.red;
      case 'medium': return Colors.orange;
      default: return Colors.blue;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: _color.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(_icon, color: _color, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(activity.title, style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    Text(activity.description, style: TextStyle(color: Colors.grey[600], fontSize: 13)),
                    const SizedBox(height: 4),
                    Text(DateFormat.yMMMd().add_jm().format(activity.timestamp), style: TextStyle(color: Colors.grey[400], fontSize: 11)),
                  ],
                ),
              ),
              if (!activity.isRead)
                Container(width: 8, height: 8, decoration: const BoxDecoration(color: Colors.blue, shape: BoxShape.circle)),
            ],
          ),
        ),
      ),
    );
  }
}

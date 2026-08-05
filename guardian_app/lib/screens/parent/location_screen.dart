import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/location_provider.dart';
import '../../models/location_model.dart';
import '../../core/theme.dart';
import 'package:uuid/uuid.dart';

class LocationScreen extends StatefulWidget {
  final String childId;
  const LocationScreen({super.key, required this.childId});

  @override
  State<LocationScreen> createState() => _LocationScreenState();
}

class _LocationScreenState extends State<LocationScreen> {
  @override
  void initState() {
    super.initState();
    final provider = context.read<LocationProvider>();
    provider.watchLocation(widget.childId);
    provider.loadHistory(widget.childId);
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<LocationProvider>();

    return Scaffold(
      appBar: AppBar(title: const Text('Location')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Icon(Icons.my_location, color: AppTheme.primaryColor),
                        const SizedBox(width: 8),
                        Text('Current Location', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (provider.latestLocation != null) ...[
                      Icon(Icons.location_on, size: 48, color: Colors.red),
                      const SizedBox(height: 8),
                      Text('${provider.latestLocation!.latitude.toStringAsFixed(4)}, ${provider.latestLocation!.longitude.toStringAsFixed(4)}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500)),
                      if (provider.latestLocation!.address != null) ...[
                        const SizedBox(height: 4),
                        Text(provider.latestLocation!.address!, style: TextStyle(color: Colors.grey[600])),
                      ],
                      const SizedBox(height: 8),
                      Text('Last updated: ${_formatTime(provider.latestLocation!.timestamp)}', style: TextStyle(color: Colors.grey[500], fontSize: 12)),
                    ] else
                      const Text('No location data available'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text('Geofences', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...provider.geofences.map((g) => Card(
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: Colors.green.withValues(alpha: 0.1),
                  child: const Icon(Icons.location_on, color: Colors.green),
                ),
                title: Text(g.name),
                subtitle: Text('${g.radiusMeters.toStringAsFixed(0)}m radius'),
                trailing: Switch(value: g.isActive, onChanged: (_) {}),
              ),
            )),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => _showAddGeofenceDialog(context),
              icon: const Icon(Icons.add),
              label: const Text('Add Geofence'),
            ),
            const SizedBox(height: 24),
            Text('Recent Locations', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...provider.history.take(5).map((loc) => ListTile(
              leading: const Icon(Icons.location_history, color: Colors.grey),
              title: Text('${loc.latitude.toStringAsFixed(4)}, ${loc.longitude.toStringAsFixed(4)}'),
              subtitle: Text(_formatTime(loc.timestamp)),
              dense: true,
            )),
          ],
        ),
      ),
    );
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }

  void _showAddGeofenceDialog(BuildContext context) {
    final nameController = TextEditingController();
    final latController = TextEditingController();
    final lngController = TextEditingController();
    final radiusController = TextEditingController(text: '100');

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add Geofence'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: nameController, decoration: const InputDecoration(labelText: 'Name', hintText: 'Home, School, etc.')),
            TextField(controller: latController, decoration: const InputDecoration(labelText: 'Latitude'), keyboardType: TextInputType.number),
            TextField(controller: lngController, decoration: const InputDecoration(labelText: 'Longitude'), keyboardType: TextInputType.number),
            TextField(controller: radiusController, decoration: const InputDecoration(labelText: 'Radius (meters)'), keyboardType: TextInputType.number),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              context.read<LocationProvider>().addGeofence(Geofence(
                id: const Uuid().v4(),
                childId: widget.childId,
                parentId: '',
                name: nameController.text,
                latitude: double.parse(latController.text),
                longitude: double.parse(lngController.text),
                radiusMeters: double.parse(radiusController.text),
                createdAt: DateTime.now(),
              ));
              Navigator.pop(ctx);
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
  }
}

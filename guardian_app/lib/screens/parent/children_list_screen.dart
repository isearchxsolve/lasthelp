import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/children_provider.dart';
import '../../core/routes.dart';
import '../../models/user_model.dart';
import '../../widgets/child/child_card.dart';

class ChildrenListScreen extends StatelessWidget {
  const ChildrenListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final childrenProvider = context.watch<ChildrenProvider>();
    return Scaffold(
      appBar: AppBar(title: const Text('Connected Children')),
      body: childrenProvider.children.isEmpty
        ? Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.child_care, size: 64, color: Colors.grey[400]),
                const SizedBox(height: 16),
                const Text('No children connected'),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: () => Navigator.pushNamed(context, AppRoutes.pairing),
                  icon: const Icon(Icons.add),
                  label: const Text('Add Child'),
                ),
              ],
            ),
          )
        : ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: childrenProvider.children.length + 1,
            itemBuilder: (context, index) {
              if (index == childrenProvider.children.length) {
                return Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.pushNamed(context, AppRoutes.pairing),
                    icon: const Icon(Icons.add),
                    label: const Text('Add Child Device'),
                  ),
                );
              }
              final child = childrenProvider.children[index];
              return ChildCard(
                child: child,
                onTap: () => Navigator.pushNamed(context, AppRoutes.parentChildDetail, arguments: child.id),
              );
            },
          ),
    );
  }
}

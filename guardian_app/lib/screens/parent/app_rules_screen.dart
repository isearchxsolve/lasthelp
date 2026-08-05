import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/app_rules_provider.dart';
import '../../models/app_rule_model.dart';
import '../../core/theme.dart';
import 'package:uuid/uuid.dart';

class AppRulesScreen extends StatefulWidget {
  final String childId;
  const AppRulesScreen({super.key, required this.childId});

  @override
  State<AppRulesScreen> createState() => _AppRulesScreenState();
}

class _AppRulesScreenState extends State<AppRulesScreen> {
  @override
  void initState() {
    super.initState();
    context.read<AppRulesProvider>().watch(widget.childId);
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<AppRulesProvider>();
    final rules = provider.rules;

    return Scaffold(
      appBar: AppBar(title: const Text('App Rules')),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddRuleDialog(context),
        child: const Icon(Icons.add),
      ),
      body: rules.isEmpty
        ? Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.apps, size: 64, color: Colors.grey[400]),
                const SizedBox(height: 16),
                const Text('No app rules set'),
                const SizedBox(height: 8),
                Text('Tap + to add rules for apps', style: TextStyle(color: Colors.grey[600])),
              ],
            ),
          )
        : ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: rules.length,
            itemBuilder: (context, index) {
              final rule = rules[index];
              return Card(
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: rule.ruleType == AppRuleType.block ? Colors.red.withValues(alpha: 0.1) : Colors.green.withValues(alpha: 0.1),
                    child: Icon(
                      rule.ruleType == AppRuleType.block ? Icons.block : Icons.check_circle,
                      color: rule.ruleType == AppRuleType.block ? Colors.red : Colors.green,
                    ),
                  ),
                  title: Text(rule.appName),
                  subtitle: Text(rule.ruleType == AppRuleType.block ? 'Blocked' : 'Allowed'),
                  trailing: IconButton(
                    icon: const Icon(Icons.delete_outline, color: Colors.red),
                    onPressed: () => provider.deleteRule(rule.id),
                  ),
                ),
              );
            },
          ),
    );
  }

  void _showAddRuleDialog(BuildContext context) {
    final appNameController = TextEditingController();
    final packageNameController = TextEditingController();
    AppRuleType ruleType = AppRuleType.block;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Add App Rule'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: appNameController,
                decoration: const InputDecoration(labelText: 'App Name', hintText: 'e.g. YouTube'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: packageNameController,
                decoration: const InputDecoration(labelText: 'Package Name', hintText: 'com.google.android.youtube'),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: ChoiceChip(
                      label: const Text('Block'),
                      selected: ruleType == AppRuleType.block,
                      onSelected: (_) => setDialogState(() => ruleType = AppRuleType.block),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ChoiceChip(
                      label: const Text('Allow'),
                      selected: ruleType == AppRuleType.allow,
                      onSelected: (_) => setDialogState(() => ruleType = AppRuleType.allow),
                    ),
                  ),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () {
                if (appNameController.text.isEmpty) return;
                final provider = context.read<AppRulesProvider>();
                provider.addRule(AppRule(
                  id: const Uuid().v4(),
                  childId: widget.childId,
                  parentId: '',
                  appPackageName: packageNameController.text.trim(),
                  appName: appNameController.text.trim(),
                  ruleType: ruleType,
                  createdAt: DateTime.now(),
                  updatedAt: DateTime.now(),
                ));
                Navigator.pop(ctx);
              },
              child: const Text('Add'),
            ),
          ],
        ),
      ),
    );
  }
}

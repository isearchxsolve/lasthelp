import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/web_filter_provider.dart';
import '../../models/web_filter_model.dart';
import '../../core/theme.dart';
import 'package:uuid/uuid.dart';

class WebFilterScreen extends StatefulWidget {
  final String childId;
  const WebFilterScreen({super.key, required this.childId});

  @override
  State<WebFilterScreen> createState() => _WebFilterScreenState();
}

class _WebFilterScreenState extends State<WebFilterScreen> {
  final _siteController = TextEditingController();

  @override
  void initState() {
    super.initState();
    context.read<WebFilterProvider>().watch(widget.childId);
  }

  @override
  void dispose() {
    _siteController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<WebFilterProvider>();
    final rule = provider.rule;

    return Scaffold(
      appBar: AppBar(title: const Text('Web Filter')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.filter_list, color: AppTheme.primaryColor),
                      const SizedBox(width: 8),
                      Text('Filter Mode', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _ModeChip(label: 'Smart Filter', desc: 'Auto-detect inappropriate content', selected: rule?.mode == WebFilterMode.smart, onTap: () => _saveMode(WebFilterMode.smart)),
                  const SizedBox(height: 8),
                  _ModeChip(label: 'Allowlist Only', desc: 'Only allow approved sites', selected: rule?.mode == WebFilterMode.allowlist, onTap: () => _saveMode(WebFilterMode.allowlist)),
                  const SizedBox(height: 8),
                  _ModeChip(label: 'Blocklist', desc: 'Block specific sites', selected: rule?.mode == WebFilterMode.blocklist, onTap: () => _saveMode(WebFilterMode.blocklist)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Content Categories to Block', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  ...ContentCategory.values.map((cat) => _CategoryToggle(
                    label: cat.name[0].toUpperCase() + cat.name.substring(1),
                    selected: rule?.blockedCategories.contains(cat) ?? [ContentCategory.adult, ContentCategory.violence, ContentCategory.gambling].contains(cat),
                    onChanged: (selected) {
                      final categories = List<ContentCategory>.from(rule?.blockedCategories ?? []);
                      if (selected) {
                        categories.add(cat);
                      } else {
                        categories.remove(cat);
                      }
                      _save(rule?.copyWith(blockedCategories: categories));
                    },
                  )),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Blocked Sites', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _siteController,
                          decoration: const InputDecoration(labelText: 'Add site URL', hintText: 'example.com'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filled(
                        icon: const Icon(Icons.add),
                        onPressed: () {
                          if (_siteController.text.trim().isNotEmpty) {
                            final sites = List<String>.from(rule?.blockedSites ?? []);
                            sites.add(_siteController.text.trim());
                            _save(rule?.copyWith(blockedSites: sites));
                            _siteController.clear();
                          }
                        },
                      ),
                    ],
                  ),
                  if (rule?.blockedSites != null)
                    ...rule!.blockedSites.map((site) => ListTile(
                      dense: true,
                      title: Text(site),
                      trailing: IconButton(
                        icon: const Icon(Icons.remove_circle_outline, color: Colors.red),
                        onPressed: () {
                          final sites = List<String>.from(rule.blockedSites);
                          sites.remove(site);
                          _save(rule.copyWith(blockedSites: sites));
                        },
                      ),
                    )),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _saveMode(WebFilterMode mode) {
    _save(context.read<WebFilterProvider>().rule?.copyWith(mode: mode));
  }

  void _save(WebFilterRule? updatedRule) {
    final provider = context.read<WebFilterProvider>();
    final rule = updatedRule ?? WebFilterRule(
      id: const Uuid().v4(),
      childId: widget.childId,
      parentId: '',
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
    provider.saveRule(rule);
  }
}

class _ModeChip extends StatelessWidget {
  final String label;
  final String desc;
  final bool selected;
  final VoidCallback onTap;
  const _ModeChip({required this.label, required this.desc, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          border: Border.all(color: selected ? AppTheme.primaryColor : Colors.grey.withValues(alpha: 0.3)),
          borderRadius: BorderRadius.circular(12),
          color: selected ? AppTheme.primaryColor.withValues(alpha: 0.05) : null,
        ),
        child: Row(
          children: [
            Radio(value: true, groupValue: selected, onChanged: (_) => onTap()),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
                Text(desc, style: TextStyle(color: Colors.grey[600], fontSize: 12)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CategoryToggle extends StatelessWidget {
  final String label;
  final bool selected;
  final ValueChanged<bool> onChanged;
  const _CategoryToggle({required this.label, required this.selected, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      title: Text(label),
      value: selected,
      dense: true,
      contentPadding: EdgeInsets.zero,
      onChanged: onChanged,
    );
  }
}

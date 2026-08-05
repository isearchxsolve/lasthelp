import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import '../../providers/screen_time_provider.dart';
import '../../models/screen_time_model.dart';
import '../../models/content_filter_model.dart';
import '../../core/theme.dart';
import 'package:uuid/uuid.dart';

class ScreenTimeScreen extends StatefulWidget {
  final String childId;
  const ScreenTimeScreen({super.key, required this.childId});

  @override
  State<ScreenTimeScreen> createState() => _ScreenTimeScreenState();
}

class _ScreenTimeScreenState extends State<ScreenTimeScreen> {
  final _limitController = TextEditingController();
  bool _isEditing = false;

  @override
  void initState() {
    super.initState();
    context.read<ScreenTimeProvider>().watch(widget.childId);
    context.read<ScreenTimeProvider>().loadRecords(widget.childId);
  }

  @override
  void dispose() {
    _limitController.dispose();
    super.dispose();
  }

  Future<void> _saveRule(ScreenTimeRule rule) async {
    await context.read<ScreenTimeProvider>().saveRule(rule);
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ScreenTimeProvider>();
    final rule = provider.rule;

    return Scaffold(
      appBar: AppBar(title: const Text('Screen Time')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _DailyLimitCard(rule: rule, childId: widget.childId, onSave: _saveRule),
            const SizedBox(height: 16),
            _BedtimeCard(rule: rule, childId: widget.childId, onSave: _saveRule),
            const SizedBox(height: 16),
            _UsageChart(records: provider.records),
            const SizedBox(height: 24),
            Text('Content Filtering', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            _ContentFilterCard(config: provider.filterConfig, childId: widget.childId, onSave: (config) => provider.saveFilterConfig(config)),
          ],
        ),
      ),
    );
  }
}

class _DailyLimitCard extends StatelessWidget {
  final ScreenTimeRule? rule;
  final String childId;
  final Function(ScreenTimeRule) onSave;
  const _DailyLimitCard({required this.rule, required this.childId, required this.onSave});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.timer, color: AppTheme.primaryColor),
                const SizedBox(width: 8),
                Text('Daily Limit', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text('${rule?.dailyLimitMinutes ?? 120} min/day', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold, color: AppTheme.primaryColor)),
                const Spacer(),
                TextButton(
                  onPressed: () => _showLimitDialog(context),
                  child: const Text('Change'),
                ),
              ],
            ),
            if (rule != null) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(
                value: 0.65,
                backgroundColor: Colors.grey[200],
                color: Colors.orange,
              ),
              const SizedBox(height: 4),
              Text('78 min used today', style: TextStyle(color: Colors.grey[600])),
            ],
          ],
        ),
      ),
    );
  }

  void _showLimitDialog(BuildContext context) {
    final controller = TextEditingController(text: '${rule?.dailyLimitMinutes ?? 120}');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Daily Screen Time Limit'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Minutes per day'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              final minutes = int.tryParse(controller.text) ?? 120;
              onSave(ScreenTimeRule(
                id: rule?.id ?? const Uuid().v4(),
                childId: childId,
                parentId: '',
                dailyLimitMinutes: minutes,
                createdAt: rule?.createdAt ?? DateTime.now(),
                updatedAt: DateTime.now(),
              ));
              Navigator.pop(ctx);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}

class _BedtimeCard extends StatelessWidget {
  final ScreenTimeRule? rule;
  final String childId;
  final Function(ScreenTimeRule) onSave;
  const _BedtimeCard({required this.rule, required this.childId, required this.onSave});

  @override
  Widget build(BuildContext context) {
    final start = rule?.bedtimeStartHour != null ? '${rule!.bedtimeStartHour!.toString().padLeft(2, '0')}:${rule!.bedtimeStartMinute!.toString().padLeft(2, '0')}' : 'Not set';
    final end = rule?.bedtimeEndHour != null ? '${rule!.bedtimeEndHour!.toString().padLeft(2, '0')}:${rule!.bedtimeEndMinute!.toString().padLeft(2, '0')}' : 'Not set';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.bedtime, color: AppTheme.secondaryColor),
                const SizedBox(width: 8),
                Text('Bedtime Schedule', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(child: Text('Start: $start', style: const TextStyle(fontSize: 16))),
                Expanded(child: Text('End: $end', style: const TextStyle(fontSize: 16))),
              ],
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => _showBedtimePicker(context),
              child: const Text('Set Schedule'),
            ),
          ],
        ),
      ),
    );
  }

  void _showBedtimePicker(BuildContext context) async {
    final startTime = await showTimePicker(context: context, initialTime: TimeOfDay(hour: rule?.bedtimeStartHour ?? 21, minute: rule?.bedtimeStartMinute ?? 0));
    if (startTime == null || !mounted) return;
    final endTime = await showTimePicker(context: context, initialTime: TimeOfDay(hour: rule?.bedtimeEndHour ?? 7, minute: rule?.bedtimeEndMinute ?? 0));
    if (endTime == null || !mounted) return;

    onSave(ScreenTimeRule(
      id: rule?.id ?? '${childId}_screen_time',
      childId: childId,
      parentId: rule?.parentId ?? '',
      dailyLimitMinutes: rule?.dailyLimitMinutes ?? 120,
      bedtimeStartHour: startTime.hour,
      bedtimeStartMinute: startTime.minute,
      bedtimeEndHour: endTime.hour,
      bedtimeEndMinute: endTime.minute,
      allowedDays: rule?.allowedDays ?? ['mon','tue','wed','thu','fri','sat','sun'],
      isActive: rule?.isActive ?? true,
      createdAt: rule?.createdAt ?? DateTime.now(),
      updatedAt: DateTime.now(),
    ));
  }
}

class _UsageChart extends StatelessWidget {
  final List<ScreenTimeRecord> records;
  const _UsageChart({required this.records});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Weekly Usage', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: PieChart(
                PieChartData(
                  sections: [
                    PieChartSectionData(value: 35, title: 'Social', color: Colors.blue, radius: 50),
                    PieChartSectionData(value: 25, title: 'Games', color: Colors.green, radius: 50),
                    PieChartSectionData(value: 20, title: 'Video', color: Colors.orange, radius: 50),
                    PieChartSectionData(value: 20, title: 'Other', color: Colors.grey, radius: 50),
                  ],
                  centerSpaceRadius: 40,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ContentFilterCard extends StatefulWidget {
  final ContentFilterConfig? config;
  final String childId;
  final Function(ContentFilterConfig) onSave;
  const _ContentFilterCard({required this.config, required this.childId, required this.onSave});

  @override
  State<_ContentFilterCard> createState() => _ContentFilterCardState();
}

class _ContentFilterCardState extends State<_ContentFilterCard> {
  bool filterImages = true;
  bool filterVideos = true;
  bool filterAudio = true;
  bool filterText = true;
  bool blurImages = true;
  bool muteAudio = true;
  bool hideVideos = true;
  bool blockText = true;
  double sensitivity = 3;

  @override
  void initState() {
    super.initState();
    if (widget.config != null) {
      filterImages = widget.config!.filterImages;
      filterVideos = widget.config!.filterVideos;
      filterAudio = widget.config!.filterAudio;
      filterText = widget.config!.filterText;
      blurImages = widget.config!.blurImages;
      muteAudio = widget.config!.muteAudio;
      hideVideos = widget.config!.hideVideos;
      blockText = widget.config!.blockText;
      sensitivity = widget.config!.imageSensitivityLevel.toDouble();
    }
  }

  void _save() {
    final cfg = ContentFilterConfig(
      id: widget.config?.id ?? const Uuid().v4(),
      childId: widget.childId,
      parentId: '',
      filterImages: filterImages,
      filterVideos: filterVideos,
      filterAudio: filterAudio,
      filterText: filterText,
      imageSensitivityLevel: sensitivity.toInt(),
      videoSensitivityLevel: sensitivity.toInt(),
      audioSensitivityLevel: sensitivity.toInt(),
      textSensitivityLevel: sensitivity.toInt(),
      blurImages: blurImages,
      muteAudio: muteAudio,
      hideVideos: hideVideos,
      blockText: blockText,
      createdAt: widget.config?.createdAt ?? DateTime.now(),
      updatedAt: DateTime.now(),
    );
    widget.onSave(cfg);
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.visibility_off, color: Colors.red),
                const SizedBox(width: 8),
                Text('Content Detection', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 4),
            Text('Auto-hide inappropriate images, videos, audio & text', style: TextStyle(color: Colors.grey[600], fontSize: 13)),
            const SizedBox(height: 16),
            _FilterToggle(label: 'Filter Images', value: filterImages, onChanged: (v) => setState(() { filterImages = v; _save(); })),
            _FilterToggle(label: 'Filter Videos', value: filterVideos, onChanged: (v) => setState(() { filterVideos = v; _save(); })),
            _FilterToggle(label: 'Filter Audio', value: filterAudio, onChanged: (v) => setState(() { filterAudio = v; _save(); })),
            _FilterToggle(label: 'Filter Text', value: filterText, onChanged: (v) => setState(() { filterText = v; _save(); })),
            const Divider(height: 24),
            Text('Sensitivity: ${sensitivity.toInt()}/5', style: const TextStyle(fontWeight: FontWeight.w500)),
            Slider(value: sensitivity, min: 1, max: 5, divisions: 4, onChanged: (v) => setState(() => sensitivity = v), onChangeEnd: (_) => _save()),
            const Divider(height: 24),
            Text('Action on Detection', style: const TextStyle(fontWeight: FontWeight.w600)),
            _FilterToggle(label: 'Blur Images', value: blurImages, onChanged: (v) => setState(() { blurImages = v; _save(); })),
            _FilterToggle(label: 'Mute Audio', value: muteAudio, onChanged: (v) => setState(() { muteAudio = v; _save(); })),
            _FilterToggle(label: 'Hide Videos', value: hideVideos, onChanged: (v) => setState(() { hideVideos = v; _save(); })),
            _FilterToggle(label: 'Block Text', value: blockText, onChanged: (v) => setState(() { blockText = v; _save(); })),
          ],
        ),
      ),
    );
  }
}

class _FilterToggle extends StatelessWidget {
  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;
  const _FilterToggle({required this.label, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      title: Text(label, style: const TextStyle(fontSize: 14)),
      value: value,
      dense: true,
      contentPadding: EdgeInsets.zero,
      onChanged: onChanged,
    );
  }
}

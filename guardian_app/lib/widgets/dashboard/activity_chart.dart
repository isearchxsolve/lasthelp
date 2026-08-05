import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';

class ActivityChart extends StatelessWidget {
  final List<double> values;
  final List<String> labels;
  final Color barColor;

  const ActivityChart({
    super.key,
    required this.values,
    required this.labels,
    this.barColor = const Color(0xFF4A6CF7),
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 200,
      child: BarChart(
        BarChartData(
          alignment: BarChartAlignment.spaceAround,
          maxY: values.isEmpty ? 10 : values.reduce((a, b) => a > b ? a : b) * 1.2,
          barGroups: values.asMap().entries.map((entry) =>
            BarChartGroupData(x: entry.key, barRods: [
              BarChartRodData(toY: entry.value, color: barColor, width: 16, borderRadius: const BorderRadius.vertical(top: Radius.circular(4))),
            ])
          ).toList(),
          titlesData: FlTitlesData(
            show: true,
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(showTitles: true, getTitlesWidget: (value, meta) {
                final idx = value.toInt();
                if (idx < 0 || idx >= labels.length) return const SizedBox.shrink();
                return Text(labels[idx], style: const TextStyle(fontSize: 10));
              }),
            ),
            leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
            topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          ),
          gridData: FlGridData(show: false),
          borderData: FlBorderData(show: false),
        ),
      ),
    );
  }
}

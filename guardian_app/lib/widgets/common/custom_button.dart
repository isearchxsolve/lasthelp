import 'package:flutter/material.dart';
import '../../core/theme.dart';

class CustomButton extends StatelessWidget {
  final String label;
  final IconData? icon;
  final bool isLoading;
  final bool isOutlined;
  final VoidCallback? onPressed;

  const CustomButton({
    super.key,
    required this.label,
    this.icon,
    this.isLoading = false,
    this.isOutlined = false,
    this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final button = isOutlined
      ? OutlinedButton.icon(
          onPressed: isLoading ? null : onPressed,
          icon: icon != null ? Icon(icon) : const SizedBox.shrink(),
          label: Text(label),
          style: OutlinedButton.styleFrom(
            minimumSize: const Size(double.infinity, 52),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        )
      : ElevatedButton.icon(
          onPressed: isLoading ? null : onPressed,
          icon: isLoading
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
            : (icon != null ? Icon(icon) : const SizedBox.shrink()),
          label: Text(label),
        );

    return button;
  }
}

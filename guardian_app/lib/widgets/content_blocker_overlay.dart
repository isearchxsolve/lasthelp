import 'dart:ui' as ui;
import 'package:flutter/material.dart';

class ContentBlockerOverlay extends StatelessWidget {
  final Widget child;
  final String? blockedReason;
  final bool isImage;
  final bool isVideo;
  final bool isAudio;
  final VoidCallback? onReportFalsePositive;

  const ContentBlockerOverlay({
    super.key,
    required this.child,
    this.blockedReason,
    this.isImage = false,
    this.isVideo = false,
    this.isAudio = false,
    this.onReportFalsePositive,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        if (isImage || isVideo) ...[
          child,
          Positioned.fill(
            child: BackdropFilter(
              filter: ui.ImageFilter.blur(sigmaX: 40, sigmaY: 40),
              child: Container(color: Colors.black.withValues(alpha: 0.3)),
            ),
          ),
          Positioned.fill(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    isImage ? Icons.image_not_supported : Icons.videocam_off,
                    size: 64,
                    color: Colors.white.withValues(alpha: 0.8),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    isImage ? 'Image Hidden' : 'Video Hidden',
                    style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  if (blockedReason != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      blockedReason!,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.7)),
                    ),
                  ],
                  if (onReportFalsePositive != null) ...[
                    const SizedBox(height: 16),
                    TextButton.icon(
                      onPressed: onReportFalsePositive,
                      icon: const Icon(Icons.flag, color: Colors.white70),
                      label: const Text('Report as safe', style: TextStyle(color: Colors.white70)),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ] else if (isAudio) ...[
          child,
          Positioned.fill(
            child: Container(color: Colors.black.withValues(alpha: 0.85)),
          ),
          Positioned.fill(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.volume_off, size: 64, color: Colors.white70),
                  const SizedBox(height: 16),
                  const Text('Audio Muted', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                  if (blockedReason != null) ...[
                    const SizedBox(height: 8),
                    Text(blockedReason!, style: TextStyle(color: Colors.white.withValues(alpha: 0.7))),
                  ],
                ],
              ),
            ),
          ),
        ] else ...[
          child,
          Positioned.fill(
            child: Container(
              color: Colors.black.withValues(alpha: 0.75),
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.block, size: 48, color: Colors.red),
                    const SizedBox(height: 16),
                    Text('Content Blocked', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
                    if (blockedReason != null) ...[
                      const SizedBox(height: 8),
                      Text(blockedReason!, style: TextStyle(color: Colors.white.withValues(alpha: 0.7))),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

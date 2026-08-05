"""
ASES - Mobile Stack Extensions
===============================
Adds React Native, Expo, Flutter, and iOS/Android support to the sandbox system.
"""

# Stack -> Docker image mapping (extended for mobile)
MOBILE_STACK_IMAGES = {
    # React Native / Expo
    "react-native": "node:18-alpine",
    "expo": "node:18-alpine",
    "expo-router": "node:18-alpine",
    # Flutter
    "flutter": "cirrusci/flutter:3.22",
    "dart": "dart:3.4",
    # Native iOS (requires macOS runner - documented limitation)
    "ios": "ghcr.io/cirruslabs/macos-sonoma-xcode:15.4",
    "swift": "ghcr.io/cirruslabs/macos-sonoma-xcode:15.4",
    # Native Android
    "android": "android:34",
    "kotlin": "gradle:8.5-jdk17",
}

# Stack -> install + test command (extended for mobile)
MOBILE_STACK_TEST_COMMANDS = {
    # React Native / Expo
    "react-native": "npm install --prefer-offline 2>&1 && npm test 2>&1",
    "expo": "npm install --prefer-offline 2>&1 && npx expo-doctor 2>&1",
    "expo-router": "npm install --prefer-offline 2>&1 && npx expo-doctor 2>&1",
    # Flutter
    "flutter": "flutter pub get 2>&1 && flutter test 2>&1",
    "dart": "dart pub get 2>&1 && dart test 2>&1",
    # Native iOS (requires macOS)
    "ios": "xcodebuild -scheme App -destination 'platform=iOS Simulator,name=iPhone 15' test 2>&1",
    "swift": "swift test 2>&1",
    # Native Android
    "android": "./gradlew test 2>&1",
    "kotlin": "./gradlew test 2>&1",
}

# Stack -> dev server commands for live preview
MOBILE_DEV_COMMANDS = {
    "react-native": "npx expo start --web --port 8081 2>&1 &",
    "expo": "npx expo start --web --port 8081 2>&1 &",
    "expo-router": "npx expo start --web --port 8081 2>&1 &",
    "flutter": "flutter run -d web-server --web-port 8081 2>&1 &",
    "dart": "dart run --port 8081 2>&1 &",
}

# Stack -> build commands for app store
MOBILE_BUILD_COMMANDS = {
    # Expo / React Native
    "expo": "npx expo build:web 2>&1",
    "expo:ios": "eas build --platform ios --profile production 2>&1",
    "expo:android": "eas build --platform android --profile production 2>&1",
    "react-native:ios": "cd ios && xcodebuild -workspace *.xcworkspace -scheme * -configuration Release 2>&1",
    "react-native:android": "cd android && ./gradlew assembleRelease 2>&1",
    # Flutter
    "flutter:web": "flutter build web 2>&1",
    "flutter:ios": "flutter build ios --release --no-codesign 2>&1",
    "flutter:android": "flutter build apk --release 2>&1",
    "flutter:appbundle": "flutter build appbundle --release 2>&1",
    # Native
    "ios": "xcodebuild -scheme App -configuration Release 2>&1",
    "android": "./gradlew assembleRelease 2>&1",
}

# Mobile-specific ports
MOBILE_PORTS = {
    "react-native": 8081,
    "expo": 8081,
    "expo-router": 8081,
    "flutter": 8081,
    "dart": 8081,
}

# App store deployment configs
APP_STORE_CONFIGS = {
    "ios": {
        "store": "app_store_connect",
        "bundle_id_pattern": "com.{tenant}.{app_name}",
        "requirements": [
            "App Store Connect API key",
            "Provisioning profile",
            "Distribution certificate",
            "App icons (1024x1024)",
            "Launch screens",
            "Privacy manifest (iOS 17+)",
        ],
        "testflight": {
            "groups": ["internal", "external"],
            "auto_distribute": True,
        },
    },
    "android": {
        "store": "play_console",
        "package_name_pattern": "com.{tenant}.{app_name}",
        "requirements": [
            "Play Console service account",
            "Keystore (upload key)",
            "App icons (512x512)",
            "Feature graphic (1024x500)",
            "Privacy policy URL",
            "Target API level 34+",
        ],
        "tracks": ["internal", "closed", "open", "production"],
    },
}

# Mobile design system extensions
MOBILE_DESIGN_SYSTEM = {
    "touch_targets": {
        "minimum": "44px",  # iOS HIG
        "recommended": "48px",  # Material Design
        "comfortable": "56px",
    },
    "safe_areas": {
        "ios": {
            "top": "44px",  # Status bar + nav
            "bottom": "34px",  # Home indicator
            "landscape_left": "44px",
            "landscape_right": "44px",
        },
        "android": {
            "top": "24px",  # Status bar
            "bottom": "0px",  # Gesture navigation
            "navigation_bar": "48px",
        },
    },
    "typography_scale": {
        "display_large": {"size": "57px", "line_height": "64px", "weight": 400},
        "display_medium": {"size": "45px", "line_height": "52px", "weight": 400},
        "display_small": {"size": "36px", "line_height": "44px", "weight": 400},
        "headline_large": {"size": "32px", "line_height": "40px", "weight": 600},
        "headline_medium": {"size": "28px", "line_height": "36px", "weight": 600},
        "headline_small": {"size": "24px", "line_height": "32px", "weight": 600},
        "title_large": {"size": "22px", "line_height": "28px", "weight": 600},
        "title_medium": {"size": "16px", "line_height": "24px", "weight": 500},
        "title_small": {"size": "14px", "line_height": "20px", "weight": 500},
        "body_large": {"size": "16px", "line_height": "24px", "weight": 400},
        "body_medium": {"size": "14px", "line_height": "20px", "weight": 400},
        "body_small": {"size": "12px", "line_height": "16px", "weight": 400},
        "label_large": {"size": "14px", "line_height": "20px", "weight": 500},
        "label_medium": {"size": "12px", "line_height": "16px", "weight": 500},
        "label_small": {"size": "11px", "line_height": "16px", "weight": 500},
    },
    "spacing_scale": [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72, 80, 96],
    "elevation": {
        "level0": "none",
        "level1": "0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08)",
        "level2": "0 3px 6px rgba(0,0,0,0.15), 0 2px 4px rgba(0,0,0,0.12)",
        "level3": "0 10px 20px rgba(0,0,0,0.15), 0 3px 6px rgba(0,0,0,0.10)",
        "level4": "0 15px 25px rgba(0,0,0,0.15), 0 5px 10px rgba(0,0,0,0.10)",
        "level5": "0 20px 40px rgba(0,0,0,0.20), 0 10px 20px rgba(0,0,0,0.15)",
    },
}

# Component library presets for mobile
MOBILE_COMPONENT_LIBRARIES = {
    "react-native": {
        "ui_kitten": {
            "name": "@ui-kitten/components",
            "theme": "@ui-kitten/theme",
            "icons": "@ui-kitten/eva-icons",
            "peer_deps": ["react-native-svg", "react-native-reanimated"],
        },
        "nativebase": {
            "name": "native-base",
            "peer_deps": ["react-native-svg", "react-native-safe-area-context", "react-native-reanimated"],
        },
        "tamagui": {
            "name": "tamagui",
            "peer_deps": ["react-native-reanimated", "react-native-gesture-handler"],
        },
        "gluestack": {
            "name": "@gluestack-ui/themed",
            "peer_deps": ["react-native-reanimated", "react-native-gesture-handler"],
        },
        "react-native-paper": {
            "name": "react-native-paper",
            "peer_deps": ["react-native-vector-icons", "react-native-safe-area-context"],
        },
    },
    "expo": {
        "expo-router": {
            "name": "expo-router",
            "peer_deps": ["expo", "expo-linking", "expo-constants"],
        },
        "expo-ui": {
            "name": "@expo/ui",
            "peer_deps": ["expo"],
        },
    },
    "flutter": {
        "material": {
            "name": "flutter/material.dart",
            "built_in": True,
        },
        "cupertino": {
            "name": "flutter/cupertino.dart",
            "built_in": True,
        },
        "flutter_riverpod": {
            "name": "flutter_riverpod",
            "state_management": True,
        },
        "get_it": {
            "name": "get_it",
            "dependency_injection": True,
        },
    },
}

# Performance budgets for mobile
MOBILE_PERF_BUDGETS = {
    "bundle_size": {
        "expo": {"warning": "500KB", "error": "1MB"},
        "react-native": {"warning": "500KB", "error": "1MB"},
        "flutter": {"warning": "2MB", "error": "5MB"},
    },
    "startup_time": {
        "cold_start": {"warning": "2s", "error": "4s"},
        "warm_start": {"warning": "500ms", "error": "1s"},
    },
    "runtime": {
        "js_heap": {"warning": "50MB", "error": "100MB"},
        "frame_rate": {"target": 60, "minimum": 55},
        "memory_leak_threshold": "10MB/min",
    },
    "lighthouse": {
        "performance": {"warning": 80, "error": 60},
        "accessibility": {"warning": 95, "error": 90},
        "best_practices": {"warning": 90, "error": 80},
        "seo": {"warning": 90, "error": 80},
    },
}

# Mobile-specific interaction patterns
MOBILE_INTERACTION_PATTERNS = {
    "gestures": [
        "swipe_left", "swipe_right", "swipe_up", "swipe_down",
        "pinch_zoom", "double_tap", "long_press", "drag_drop",
        "pull_to_refresh", "edge_swipe_back",
    ],
    "navigation": [
        "stack_push", "stack_pop", "stack_replace",
        "tab_switch", "drawer_open", "drawer_close",
        "modal_present", "modal_dismiss",
        "deep_link", "universal_link",
    ],
    "platform_specific": {
        "ios": [
            "haptic_feedback", "3d_touch", "back_swipe",
            "dynamic_island", "live_activity",
        ],
        "android": [
            "haptic_feedback", "back_gesture", "predictive_back",
            "edge_to_edge", "splash_screen_api",
        ],
    },
}

# Accessibility requirements for mobile
MOBILE_A11Y_REQUIREMENTS = {
    "ios": {
        "voiceover": True,
        "dynamic_type": True,
        "reduce_motion": True,
        "reduce_transparency": True,
        "invert_colors": True,
        "bold_text": True,
        "button_shapes": True,
        "on_off_labels": True,
    },
    "android": {
        "talkback": True,
        "font_scale": True,
        "remove_animations": True,
        "high_contrast": True,
        "color_inversion": True,
        "magnification": True,
        "select_to_speak": True,
        "switch_access": True,
    },
    "common": {
        "touch_target_min": "44px",
        "contrast_ratio": "4.5:1",
        "focus_indicator": True,
        "semantic_labels": True,
        "heading_structure": True,
        "landmarks": True,
        "live_regions": True,
    },
}
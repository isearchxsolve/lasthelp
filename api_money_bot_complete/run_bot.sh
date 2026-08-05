#!/bin/bash
# API Money Bot v3.0 — Linux/Mac Launcher
# ========================================
# Menu-driven interface for running the bot

set -e

show_menu() {
    clear
    echo "═══════════════════════════════════════════════════════════"
    echo "   API MONEY BOT v3.0 — PAYMENT AUTOMATION EDITION"
    echo "═══════════════════════════════════════════════════════════"
    echo
    echo "   [1] Health Check (validate credentials)"
    echo "   [2] Safe Monitoring Run (read-only, no money moves)"
    echo "   [3] Revenue Summary"
    echo "   [4] Run API Key Harvester (all platforms)"
    echo "   [5] Run API Key Harvester (specific platforms)"
    echo "   [6] Show Harvested Keys"
    echo "   [7] Single Platform Run (interactive)"
    echo "   [8] Live Action (requires LIVE_MODE=true)"
    echo "   [9] Exit"
    echo
    echo "═══════════════════════════════════════════════════════════"
}

run_health() {
    echo
    echo "Running Health Check..."
    echo
    python src/api_money_bot_v3.py --health
    echo
    read -p "Press Enter to continue..."
}

run_monitor() {
    echo
    echo "Running Safe Monitoring (LIVE_MODE=false)..."
    echo
    python src/api_money_bot_v3.py
    echo
    read -p "Press Enter to continue..."
}

run_summary() {
    echo
    echo "Generating Revenue Summary..."
    echo
    python src/api_money_bot_v3.py --summary
    echo
    read -p "Press Enter to continue..."
}

run_harvest_all() {
    echo
    echo "Harvesting ALL platform keys..."
    echo
    python api_key_harvester/main.py
    echo
    read -p "Press Enter to continue..."
}

run_harvest_specific() {
    echo
    read -p "Enter platform names (space-separated, e.g. binance coinbase github): " PLATFORMS
    python api_key_harvester/main.py --platforms $PLATFORMS
    echo
    read -p "Press Enter to continue..."
}

run_show_keys() {
    echo
    echo "Showing Harvested Keys..."
    echo
    python api_key_harvester/main.py --show
    echo
    read -p "Press Enter to continue..."
}

run_single_platform() {
    echo
    echo "Available platforms:"
    echo "  binance coinbase kucoin bybit okx"
    echo "  upwork freelancer reddit"
    echo "  shutterstock adobestock pond5"
    echo "  gumroad etsy ebay stripe"
    echo "  shopify printful printify"
    echo "  youtube medium openai anthropic replicate"
    echo "  razorpay wise paypal"
    echo "  toloka clickworker remotasks"
    echo
    read -p "Enter platform name: " PLATFORM
    python src/api_money_bot_v3.py --platform "$PLATFORM"
    echo
    read -p "Press Enter to continue..."
}

run_live_action() {
    echo
    echo "⚠️  WARNING: This requires LIVE_MODE=true in .env"
    echo "⚠️  No money moves unless LIVE_MODE=true and category flags are enabled!"
    echo
    echo "Available actions per platform:"
    echo "  Binance: execute_trade '{\"symbol\":\"BTCUSDT\",\"side\":\"BUY\",\"quantity\":0.001}'"
    echo "  (Check platform class for more actions)"
    echo
    read -p "Enter platform: " PLATFORM
    read -p "Enter action method: " ACTION
    read -p "Enter JSON args (optional): " ARGS
    if [ -z "$ARGS" ]; then
        LIVE_MODE=true python src/api_money_bot_v3.py --platform "$PLATFORM" --action "$ACTION"
    else
        LIVE_MODE=true python src/api_money_bot_v3.py --platform "$PLATFORM" --action "$ACTION" --args "$ARGS"
    fi
    echo
    read -p "Press Enter to continue..."
}

# Main loop
while true; do
    show_menu
    read -p "Select option [1-9]: " CHOICE
    case $CHOICE in
        1) run_health ;;
        2) run_monitor ;;
        3) run_summary ;;
        4) run_harvest_all ;;
        5) run_harvest_specific ;;
        6) run_show_keys ;;
        7) run_single_platform ;;
        8) run_live_action ;;
        9) echo "Goodbye!"; sleep 1; exit 0 ;;
        *) echo "Invalid option. Press Enter to continue..."; read ;;
    esac
done
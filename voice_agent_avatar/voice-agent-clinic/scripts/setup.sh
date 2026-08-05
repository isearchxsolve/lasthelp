#!/bin/bash
# Quick setup script for new clients

set -e

echo "=== Voice Agent Clinic — Client Setup ==="

# Get inputs
read -p "Business name: " BUSINESS_NAME
read -p "Vertical (dental/medical/hvac/legal/real_estate): " VERTICAL
read -p "Cal.com event type ID: " EVENT_TYPE_ID
read -p "Twilio phone number (+1234567890): " TWILIO_PHONE
read -p "Email for notifications: " NOTIFICATION_EMAIL

echo ""
echo "Setting up configuration for $BUSINESS_NAME..."

# Create config directory
mkdir -p "configs/$BUSINESS_NAME"

# Generate config file
cat > "configs/$BUSINESS_NAME/config.yaml" <<EOF
business_name: "$BUSINESS_NAME"
vertical: "$VERTICAL"
calcom_event_type_id: $EVENT_TYPE_ID
twilio_phone: "$TWILIO_PHONE"
notification_email: "$NOTIFICATION_EMAIL"
enabled: true
EOF

echo "Config created at: configs/$BUSINESS_NAME/config.yaml"
echo ""
echo "Next steps:"
echo "1. Add FAQ entries to configs/$BUSINESS_NAME/faq.json"
echo "2. Set environment variables in .env"
echo "3. Run: docker-compose up -d"
echo ""
echo "Setup complete!"

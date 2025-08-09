#!/bin/bash

echo "==================================="
echo "Stock Signal Bot - Render Deployment"
echo "==================================="

if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please create a .env file with required credentials"
    exit 1
fi

echo "Checking required environment variables..."
required_vars=("FMP_API_KEY" "TELEGRAM_BOT_TOKEN" "TELEGRAM_CHAT_ID")
for var in "${required_vars[@]}"; do
    if ! grep -q "^$var=" .env; then
        echo "Error: $var not found in .env file"
        exit 1
    fi
done
echo "✓ All required environment variables found"

echo ""
echo "📋 Pre-deployment checklist:"
echo "1. Have you created a Render account?"
echo "2. Have you installed Render CLI? (npm install -g @render-cli/cli)"
echo "3. Have you logged in to Render CLI? (render login)"
echo ""
read -p "Continue with deployment? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

echo ""
echo "🚀 Deploying to Render..."
echo ""
echo "Follow these steps:"
echo ""
echo "1. Go to https://dashboard.render.com/new"
echo "2. Connect your GitHub/GitLab repository"
echo "3. Select 'Web Service'"
echo "4. Use these settings:"
echo "   - Name: stock-signal-bot"
echo "   - Region: Oregon (US West)"
echo "   - Branch: main"
echo "   - Runtime: Python 3"
echo "   - Build Command: pip install -r requirements.txt"
echo "   - Start Command: python render_web_wrapper.py"
echo "   - Instance Type: Starter ($7/month)"
echo ""
echo "5. Add environment variables from .env file:"
echo ""

while IFS='=' read -r key value; do
    if [[ ! -z "$key" && ! "$key" =~ ^# ]]; then
        echo "   - $key: [Set in Render dashboard]"
    fi
done < .env

echo ""
echo "6. Click 'Create Web Service'"
echo ""
echo "Alternative: Use render.yaml for automatic configuration"
echo "   - Commit all files to your repository"
echo "   - Render will auto-detect render.yaml"
echo ""
echo "📌 Important Notes:"
echo "- Render Starter plan has 512MB RAM limit"
echo "- Bot is optimized for this constraint"
echo "- FMP Free tier: 250 API calls/day"
echo "- Consider upgrading FMP for more frequent scans"
echo ""
echo "✅ Deployment preparation complete!"
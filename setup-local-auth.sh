#!/bin/bash

# Local Authentication Setup Script
# This script reads ACCESS_PASSWORD from .env and updates auth-config.js with the SHA-256 hash

set -e

echo "🔐 Setting up local authentication..."

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create .env file with ACCESS_PASSWORD=your_password"
    exit 1
fi

# Load environment variables from .env
export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)

# Check if ACCESS_PASSWORD is set
if [ -z "$ACCESS_PASSWORD" ]; then
    echo "⚠️  ACCESS_PASSWORD is not set in .env file"
    echo "Password protection will be disabled"
    PASSWORD_HASH="DISABLED_NO_PASSWORD_SET_IN_SECRETS"
else
    echo "✅ Found ACCESS_PASSWORD in .env"

    # Generate SHA-256 hash using openssl
    if command -v openssl &> /dev/null; then
        PASSWORD_HASH=$(echo -n "$ACCESS_PASSWORD" | openssl dgst -sha256 -hex | awk '{print $2}')
        echo "✅ Generated SHA-256 hash using openssl"
    # Fallback to shasum if openssl is not available
    elif command -v shasum &> /dev/null; then
        PASSWORD_HASH=$(echo -n "$ACCESS_PASSWORD" | shasum -a 256 | awk '{print $1}')
        echo "✅ Generated SHA-256 hash using shasum"
    else
        echo "❌ Error: Neither openssl nor shasum is available"
        echo "Please install openssl or shasum to generate password hash"
        exit 1
    fi
fi

# Backup original auth-config.js if it exists and hasn't been backed up yet
if [ -f "web/js/auth-config.js" ] && [ ! -f "web/js/auth-config.js.backup" ]; then
    cp web/js/auth-config.js web/js/auth-config.js.backup
    echo "📦 Backed up original auth-config.js"
fi

# Update auth-config.js with the generated hash
if [ -f "web/js/auth-config.js" ]; then
    # Replace PLACEHOLDER_PASSWORD_HASH with actual hash
    sed -i.tmp "s/passwordHash: '.*'/passwordHash: '$PASSWORD_HASH'/" web/js/auth-config.js
    rm -f web/js/auth-config.js.tmp
    echo "✅ Updated web/js/auth-config.js with password hash"
else
    echo "❌ Error: web/js/auth-config.js not found!"
    exit 1
fi

echo ""
echo "🎉 Local authentication setup complete!"
echo ""
echo "📝 Summary:"
echo "  - Password hash: ${PASSWORD_HASH:0:16}..."
echo "  - Config file: web/js/auth-config.js"
echo ""
echo "💡 Tips:"
echo "  - Open web/login.html in browser to test"
echo "  - Use password from .env to login"
echo "  - auth-config.js is gitignored and won't be committed"
echo ""

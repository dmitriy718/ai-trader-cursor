#!/bin/bash
# Setup script for AI Trading Bot

set -e

echo "🚀 Setting up AI Trading Bot..."

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data logs models config

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your Binance API credentials!"
fi

# Create dummy ML model if it doesn't exist
if [ ! -f models/price_predictor.tflite ]; then
    echo "🤖 Creating dummy ML model..."
    python scripts/create_dummy_model.py --output models/price_predictor.tflite || echo "⚠️  Could not create model (TensorFlow may not be installed)"
fi

# Set permissions
chmod +x scripts/*.py
chmod +x scripts/*.sh

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your Binance API credentials"
echo "2. Review config/config.yaml for trading parameters"
echo "3. Run: docker-compose build"
echo "4. Run: docker-compose up -d"
echo "5. Access dashboard at: http://localhost:8000"

#!/bin/bash

echo "🧪 Testing Webscout backend..."

# Test search endpoint
echo "Testing /search endpoint..."
curl -s -X POST http://localhost:5000/search \
  -H "Content-Type: application/json" \
  -d '{"query":"github security"}' | head -50

# Test gather-repo endpoint
echo -e "\n\nTesting /gather-repo endpoint..."
curl -s -X POST http://localhost:5000/gather-repo \
  -H "Content-Type: application/json" \
  -d '{"owner":"facebook","repo":"react"}' | head -50

echo -e "\n\n✅ Test complete!"

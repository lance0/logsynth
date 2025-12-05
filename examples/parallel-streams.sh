#!/bin/bash
# Example: Per-Stream Rate Configuration
# Demonstrates running multiple log streams with different rates
#
# This script shows various ways to use the --stream option

echo "=== Example 1: Different rates per stream ==="
echo "Running nginx at 50/sec, redis at 10/sec for 5 seconds"
logsynth run nginx redis \
  --stream nginx:rate=50 \
  --stream redis:rate=10 \
  --duration 5s

echo ""
echo "=== Example 2: Different formats per stream ==="
echo "Running nginx as JSON, postgres as plain text"
logsynth run nginx postgres \
  --stream nginx:rate=20,format=json \
  --stream postgres:rate=10,format=plain \
  --duration 3s

echo ""
echo "=== Example 3: Three streams with varying rates ==="
echo "High-traffic web + medium database + low security audit"
logsynth run nginx mysql auth \
  --stream nginx:rate=100 \
  --stream mysql:rate=25 \
  --stream auth:rate=5 \
  --duration 3s

echo ""
echo "=== Example 4: Using count mode with per-stream counts ==="
echo "Generate specific number of logs per stream"
logsynth run nginx redis \
  --stream nginx:count=50 \
  --stream redis:count=20 \
  --count 100  # Total count, distributed if not specified per-stream

#!/bin/bash
# VM Deployment Script for Search Agent

echo "Starting Search Agent deployment on VM..."

# 1. System Updates
echo "Updating system..."
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Prerequisites
echo "Installing prerequisites (curl, python3, pip, nodejs, npm)..."
sudo apt-get install -y curl python3 python3-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# 3. Setup Backend
echo "Setting up Backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Deploying Python Backend as systemd service (stub)..."
# Typically you'd create a systemd service file here running: `uvicorn src.main:app --host 0.0.0.0 --port 8000`
cd ..

# 4. Setup Frontend
echo "Setting up Frontend..."
cd frontend
npm install
npm run build
echo "Deploying Next.js Frontend as systemd service (stub)..."
# Typically you'd create a systemd service file here running: `npm start`
cd ..

echo "Deployment complete! Ensure ports 8000 (Backend) and 3000 (Frontend) are accessible."

# Search Agent

A powerful, multimodal, and highly modular Agent application designed to ingest files/text into a local vector semantic network and expose that knowledge both to humans (via a Next.js UI) and other agents (via MCP and custom REST endpoints).

## Architecture overview
- **Frontend Dashboard (`/frontend`)**: Next.js App Router application constructed using Tailwind CSS glassmorphism aesthetics.
- **Backend Services (`/backend`)**: Python FastAPI backend employing strict Interfaces (Abstract Base Classes) for Embedders, Chunkers, and Vector Databases.
- **Semantic Storage**: Natively integrates `Qdrant` for powerful hybrid (dense+sparse) search capabilities, smoothly falling back to a highly-available `ChromaDB` integration if Qdrant fails.

## Running the Application

### 1. Local Development (Dual Terminals)

**Backend Terminal**:
```bash
cd backend
source ~/.bashrc
pyenv activate awsworkshop # Ensure Python 3.11+ is active
pip install -r requirements.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend Terminal**:
```bash
cd frontend
npm install
npm run dev
```
Navigate to `http://localhost:3000` to access the agent UI.

### 2. VM Deployment Script
A bash script (`deploy_vm.sh`) is provided for automated bare-metal/VM deployments.
```bash
chmod +x deploy_vm.sh
./deploy_vm.sh
```

### 3. Container Deployment (Docker Compose)
To launch the entire stack as isolated containers, ensure Docker is installed and run:
```bash
docker-compose up --build -d
```
- The Dashboard will be active at `http://localhost:3000`
- The Agent/API endpoints will be active at `http://localhost:8000`
- Data is persistently stored in Docker volumes mapped to `./backend/qdrant_data` and `./backend/chroma_data`

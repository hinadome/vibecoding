# Search Agent UI (Frontend)

## Overview
This is the Next.js frontend for the Search Agent. It provides a highly interactive, aesthetic dashboard for users to upload documents (PDF/Text), configure parsing hyperparameters, and query the agent's vector database semantic network.

## Features
- **Glassmorphism Design:** Modern UI with deep dark mode tailwind styling.
- **Ingestion Controls:** Adjust chunk sizes and overlap dynamically before uploading.
- **Hybrid Search Interface:** View parsed documents alongside their semantic similarity scores.

## Setup & Execution

### Prerequisites
- Node.js (v18+)
- npm or pnpm

### Installation
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```

### Running Locally
To run the development server:
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the outcome.

### Production Build
```bash
npm run build
npm start
```

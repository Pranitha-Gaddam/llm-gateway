# LLM Gateway Proxy

A high-performance AI reverse proxy with a optimized two-tier caching architecture.

---

## 🧠 Caching Architecture

1. **Tier 1: Global Exact Match (Stateless)**
   * **Scope:** First-turn user prompts only.
   * **Logic:** Matches identical strings globally to bypass embedding generation and upstream LLM calls. Protected by a guard clause that completely skips history threads to prevent cache pollution.

2. **Tier 2: Semantic Vector Match (Stateful)**
   * **Scope:** Multi-turn conversational threads.
   * **Logic:** Computes a vector embedding on a rolling context anchor string (`System Prompt` + `Last Assistant Response` + `Current User Prompt`) and executes a K-Nearest Neighbors (KNN) search against a Redis Stack JSON index using a strict cosine distance threshold (`0.15`).

---

## ⚡ Commands to Run

### 1. Start Infrastructure
Spin up the background Redis Stack database container:
```bash
docker-compose up -d
```
### 2. Launch the server
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --loop uvloop --http httptools
```

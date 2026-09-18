<div align="center">

# 🧠 Project Atlas

### AI-Native Knowledge Engineering Platform

Continuously acquire, process, enrich, index, and serve enterprise knowledge for downstream Generative AI applications.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![License](https://img.shields.io/badge/license-private-lightgrey)
![Python](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)
![Neo4j](https://img.shields.io/badge/graph-Neo4j-008CC1?logo=neo4j&logoColor=white)
![Qdrant](https://img.shields.io/badge/vector--db-Qdrant-DC244C)
![Kubernetes](https://img.shields.io/badge/deploy-Kubernetes-326CE5?logo=kubernetes&logoColor=white)

</div>

---

## 📖 About

**Project Atlas** ingests knowledge from public sources (PubMed, WHO, CDC, NIH, DailyMed, government advisories) and turns it into a searchable, enriched knowledge graph + vector index for downstream GenAI apps — while remaining fully **domain-independent**.

**Pipeline:**
```
Data Sources → Acquisition → Validation → Deduplication → Parsing 
→ Metadata Extraction → Entity Extraction → Knowledge Graph 
→ Chunking → Embedding Generation → Vector Index → Evaluation → API
```

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| Workflow Orchestration | Temporal |
| Streaming | Apache Kafka |
| Crawling | Playwright, Crawl4AI, Firecrawl |
| Document Parsing | Unstructured |
| Structured Extraction | Instructor + LLM |
| Knowledge Graph | Neo4j |
| Vector Database | Qdrant |
| Metadata Store | PostgreSQL |
| Object Storage | MinIO / Amazon S3 |
| LLM Gateway | LiteLLM |
| Evaluation | Ragas + DeepEval |
| Observability | Langfuse |
| Frontend | Next.js |
| Deployment | Kubernetes |

---

## 📂 Repository Structure

```
Project-Atlas/
├── api-connector/               # API-based data source connectors
├── bulk-download/               # Bulk dataset downloads (XML/CSV dumps)
├── web-crawling/                # Scheduled web crawlers
├── manual-onboarding/           # Manual document upload pipeline
├── data-ingestion/              # Ingestion job scheduling & execution
├── document-parsing/            # Document normalization & parsing
├── knowledge-graph/             # Neo4j schema & graph models
├── metadata-knowledge/          # Metadata & entity extraction
├── ai-retrieval-embeddings/     # Embeddings & semantic retrieval
├── llm-platform/                # LLM gateway & enrichment
├── workflow-event-processing/   # Temporal workflows, Kafka events
├── backend-data-services/       # Core backend data services
├── infra/                       # CI/CD, Docker, Kubernetes manifests
└── docs/                        # Architecture & planning docs
```

---

## 👥 Contributors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/vishalkannsgit"><img src="https://github.com/vishalkannsgit.png" width="90" style="border-radius:50%"/><br><b>Vishal Kanna</b></a><br>
      <sub>Knowledge Graph</sub>
    </td>
    <td align="center">
      <a href="https://github.com/hari-harann"><img src="https://github.com/hari-harann.png" width="90" style="border-radius:50%"/><br><b>Hariharan</b></a><br>
      <sub>AI Retrieval & Embeddings</sub>
    </td>
    <td align="center">
      <a href="https://github.com/pritheshwar12"><img src="https://github.com/pritheshwar12.png" width="90" style="border-radius:50%"/><br><b>Pritheshwar</b></a><br>
      <sub>Metadata & Knowledge</sub>
    </td>
    <td align="center">
      <a href="https://github.com/Ajaymkp"><img src="https://github.com/Ajaymkp.png" width="90" style="border-radius:50%"/><br><b>Mukesh</b></a><br>
      <sub>Bulk Download</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <b>Rajiv</b><br>
      <sub>Manual Onboarding</sub>
    </td>
    <td align="center">
      <b>Prakash</b><br>
      <sub>Workflow & Event Processing</sub>
    </td>
    <td align="center">
      <a href="https://github.com/AK-RK7"><img src="https://github.com/AK-RK7.png" width="90" style="border-radius:50%"/><br><b>AK-RK7</b></a><br>
      <sub>Backend Data Services</sub>
    </td>
    <td align="center">
      <a href="https://github.com/Sreedharan1998"><img src="https://github.com/Sreedharan1998.png" width="90" style="border-radius:50%"/><br><b>Sreedharan</b></a><br>
      <sub>API Connector</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="https://github.com/Ashok6116"><img src="https://github.com/Ashok6116.png" width="90" style="border-radius:50%"/><br><b>Ashok</b></a><br>
      <sub>Web Crawling</sub>
    </td>
    <td align="center">
      <b>Kuyilan</b><br>
      <sub>Data Ingestion</sub>
    </td>
    <td align="center">
      <a href="https://github.com/saisiddarth95147-creator"><img src="https://github.com/saisiddarth95147-creator.png" width="90" style="border-radius:50%"/><br><b>Sai Sidharth</b></a><br>
      <sub>Document Parsing</sub>
    </td>
    <td align="center">
      <a href="https://github.com/Ashwathnar"><img src="https://github.com/Ashwathnar.png" width="90" style="border-radius:50%"/><br><b>Ashwath</b></a><br>
      <sub>LLM Platform</sub>
    </td>
  </tr>
</table>

---

## 🌳 Branching Convention

Each module is developed on its own feature branch and merged into `master` via a **Pull Request**, requiring **1 approval** before merging.

| Branch | Owner |
|---|---|
| `feature/api-connector` | Sreedharan |
| `feature/bulk-download` | Mukesh |
| `feature/web-crawling` | Ashok |
| `feature/manual-onboarding` | Rajiv |
| `feature/data-ingestion` | Kuyilan |
| `feature/document-parsing` | Sai Sidharth |
| `feature/knowledge-graph` | Vishal |
| `feature/metadata-knowledge` | Pritheshwar |
| `feature/ai-retrieval-embeddings` | Hariharan |
| `feature/llm-platform` | Ashwath |
| `feature/workflow-event-processing` | Prakash |
| `feature/backend-data-services` | AK-RK7 |

```bash
git clone https://github.com/vishalkannsgit/Project-Atlas.git
cd Project-Atlas
git checkout feature/<your-module>
# work inside your module folder
git add .
git commit -m "your message"
git push origin feature/<your-module>
```

---

<div align="center">

**Built by Team Sreedharan & Team Hariharan** 🚀

</div>

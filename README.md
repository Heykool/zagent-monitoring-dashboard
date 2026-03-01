# ZAgent Monitoring Dashboard

Local monitoring dashboard for OpenClaw agents with memory flow visualization.

## Features

- **Agent Status Monitoring**: Track sessions, workspaces, memory files, and config files
- **System Metrics**: CPU, RAM, Disk usage
- **Memory Flow Diagrams**: Visual representation of dual memory system per agent
- **REST API**: Programmatic access to all data

## Running

```bash
cd agent-dashboard
source venv/bin/activate
python3 dashboard.py
```

Access at http://localhost:5000

## Memory Flow Diagrams

Each agent has a visual flow diagram showing:

- **Input**: User input and external API data
- **Dual Memory Processing**: v3 local files + Qdrant vector DB
- **Storage Layer**: Where data is persisted
- **Retrieval**: How data is recalled (fast local vs semantic vector search)
- **Cleanup**: Retention policies

### Agent Configurations

| Agent | Role | Max Tokens | Recall Speed | Storage Limit |
|-------|------|------------|--------------|---------------|
| zjuniorcoder | Implementation | 8,000 | 150ms | 50MB |
| zseniorcoder | Architecture | 12,000 | 200ms | 100MB |
| zpredictor | Prediction | 6,000 | 100ms | 200MB |
| zhypetrader | Trading | 4,000 | 50ms | 500MB |

## API Endpoints

- `GET /api/agents` - All agent status
- `GET /api/metrics` - System metrics
- `GET /api/gateway` - Gateway status
- `GET /api/memory` - Memory data for all agents
- `GET /api/memory/<agent_id>` - Memory data for specific agent
- `GET /api/memory-flow/<agent_id>` - Mermaid diagram for agent

## Testing

```bash
python3 test_dashboard.py
```

25 unit tests covering:
- Agent memory configurations
- Mermaid flow diagram generation
- Flask API routes
- Efficiency parameters validation
#!/usr/bin/env python3
"""
Agent Dashboard - Local monitoring for OpenClaw agents
Run: python3 dashboard.py
Access: http://localhost:5000 or http://<your-ip>:5000

Features:
- Agent status monitoring
- System metrics
- Memory flow diagrams (Dual memory: v3 local + Qdrant vector DB)
- Efficiency parameters per agent
"""

import os
import json
import psutil
import socket
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# Configuration
AGENTS_DIR = "/root/.openclaw/agents"
WORKSPACE_DIR = "/root/.openclaw/workspace"

# Agent memory configurations
AGENT_MEMORY_CONFIG = {
    "zjuniorcoder": {
        "name": "Junior Coder",
        "role": "Implementation & coding tasks",
        "local_storage": {
            "path": "memory/",
            "files": ["MEMORY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md"],
            "retention": "30 days for daily notes, permanent for MEMORY.md"
        },
        "vector_db": {
            "collection": "zjuniorcoder_memories",
            "dimensions": 1536,
            "retention": "90 days or until importance < 0.3"
        },
        "efficiency": {
            "max_tokens_per_context": 8000,
            "target_recall_speed_ms": 150,
            "storage_limit_mb": 50
        }
    },
    "zseniorcoder": {
        "name": "Senior Coder",
        "role": "Architecture & code review",
        "local_storage": {
            "path": "memory/",
            "files": ["MEMORY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md"],
            "retention": "60 days for daily notes, permanent for MEMORY.md"
        },
        "vector_db": {
            "collection": "zseniorcoder_memories",
            "dimensions": 1536,
            "retention": "180 days or until importance < 0.2"
        },
        "efficiency": {
            "max_tokens_per_context": 12000,
            "target_recall_speed_ms": 200,
            "storage_limit_mb": 100
        }
    },
    "zpredictor": {
        "name": "Predictor",
        "role": "Market prediction & analysis",
        "local_storage": {
            "path": "memory/",
            "files": ["MEMORY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md", "predictions/"],
            "retention": "14 days for daily notes, 90 days for predictions"
        },
        "vector_db": {
            "collection": "zpredictor_memories",
            "dimensions": 1536,
            "retention": "60 days or until importance < 0.4"
        },
        "efficiency": {
            "max_tokens_per_context": 6000,
            "target_recall_speed_ms": 100,
            "storage_limit_mb": 200
        }
    },
    "zhypetrader": {
        "name": "Hyper Trader",
        "role": "High-frequency trading automation",
        "local_storage": {
            "path": "memory/",
            "files": ["MEMORY.md", "SOUL.md", "AGENTS.md", "USER.md", "trades/", "cycles/"],
            "retention": "7 days for cycle logs, 30 days for trade history"
        },
        "vector_db": {
            "collection": "zhypetrader_memories",
            "dimensions": 1536,
            "retention": "30 days or until importance < 0.5"
        },
        "efficiency": {
            "max_tokens_per_context": 4000,
            "target_recall_speed_ms": 50,
            "storage_limit_mb": 500
        }
    }
}


def get_agent_status(agent_id):
    """Get status for a single agent."""
    agent_path = os.path.join(AGENTS_DIR, agent_id)
    workspace_path = os.path.join(WORKSPACE_DIR, f"workspace-{agent_id}")
    
    status = {
        "id": agent_id,
        "name": agent_id.replace("z", "").title(),
        "status": "unknown",
        "sessions": 0,
        "last_active": None,
        "has_workspace": os.path.exists(workspace_path),
        "memory_files": 0,
        "config_files": 0,
    }
    
    # Check agent directory
    if os.path.exists(agent_path):
        # Count sessions
        sessions_path = os.path.join(agent_path, "sessions")
        if os.path.exists(sessions_path):
            try:
                sessions = os.listdir(sessions_path)
                status["sessions"] = len(sessions)
            except:
                pass
        
        # Check for agent state file
        state_file = os.path.join(agent_path, "agent", "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file) as f:
                    state = json.load(f)
                    status["last_active"] = state.get("lastActive", None)
            except:
                pass
    
    # Check workspace
    if os.path.exists(workspace_path):
        # Count memory files
        memory_path = os.path.join(workspace_path, "memory")
        if os.path.exists(memory_path):
            try:
                status["memory_files"] = len([f for f in os.listdir(memory_path) if f.endswith(".md")])
            except:
                pass
        
        # Check for config files
        for f in ["SOUL.md", "AGENTS.md", "MEMORY.md", "SKILL.md"]:
            if os.path.exists(os.path.join(workspace_path, f)):
                status["config_files"] += 1
    
    # Determine status based on recent activity
    if status["sessions"] > 0 or status["last_active"]:
        status["status"] = "active"
    else:
        status["status"] = "inactive"
    
    return status


def get_all_agents():
    """Get all agents."""
    agents = []
    if os.path.exists(AGENTS_DIR):
        for item in os.listdir(AGENTS_DIR):
            item_path = os.path.join(AGENTS_DIR, item)
            if os.path.isdir(item_path) and not item.startswith("."):
                agents.append(item)
    return sorted(agents)


def get_system_metrics():
    """Get system metrics."""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        
        return {
            "cpu_percent": cpu,
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024**3), 1),
            "memory_total_gb": round(memory.total / (1024**3), 1),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
        }
    except:
        return {}


def get_gateway_status():
    """Check if gateway is running."""
    try:
        import requests
        resp = requests.get("http://localhost:18789/health", timeout=2)
        return "online" if resp.status_code == 200 else "offline"
    except:
        return "offline"


def get_memory_flow_data(agent_id):
    """Get memory flow data for a specific agent."""
    workspace_path = os.path.join(WORKSPACE_DIR, f"workspace-{agent_id}")
    
    # Get agent config
    config = AGENT_MEMORY_CONFIG.get(agent_id, {
        "name": agent_id.replace("z", "").title(),
        "role": "General purpose agent",
        "local_storage": {"path": "memory/", "files": [], "retention": "30 days"},
        "vector_db": {"collection": f"{agent_id}_memories", "dimensions": 1536, "retention": "90 days"},
        "efficiency": {"max_tokens_per_context": 5000, "target_recall_speed_ms": 150, "storage_limit_mb": 50}
    })
    
    # Count actual files
    memory_files = []
    storage_size = 0
    
    if os.path.exists(workspace_path):
        memory_path = os.path.join(workspace_path, "memory")
        if os.path.exists(memory_path):
            for f in os.listdir(memory_path):
                if f.endswith(".md"):
                    fpath = os.path.join(memory_path, f)
                    try:
                        size = os.path.getsize(fpath)
                        storage_size += size
                        memory_files.append({
                            "name": f,
                            "size_bytes": size,
                            "size_kb": round(size / 1024, 1)
                        })
                    except:
                        pass
    
    return {
        "agent_id": agent_id,
        "config": config,
        "memory_files": memory_files,
        "total_storage_bytes": storage_size,
        "total_storage_kb": round(storage_size / 1024, 1),
        "file_count": len(memory_files)
    }


def generate_mermaid_flow(agent_id):
    """Generate Mermaid.js flow diagram for agent memory."""
    config = AGENT_MEMORY_CONFIG.get(agent_id, {})
    name = config.get("name", agent_id.replace("z", "").title())
    
    # Get retention policies
    local_retention = config.get("local_storage", {}).get("retention", "30 days")
    vector_retention = config.get("vector_db", {}).get("retention", "90 days")
    
    # Get vector collection name
    vector_collection = config.get("vector_db", {}).get("collection", f"{agent_id}_memories")
    
    diagram = f"""```mermaid
flowchart LR
    subgraph Input["Data Input"]
        User[("User Input")] --> Session
        External[("External APIs")] --> Session
    end
    
    subgraph Processing["Dual Memory Processing"]
        Session -->|Store| DualMem[("Dual Memory System")]
        DualMem -->|Write| Local[(Local Files v3)]
        DualMem -->|Write| Vector[(Qdrant Vector DB)]
    end
    
    subgraph Storage["Storage Layer"]
        Local -->|JSON/Markdown| LocalFiles[("memory/*.md")]
        Vector -->|Embeddings| VectorCollection["({vector_collection})"]
    end
    
    subgraph Retrieval["Retrieval"]
        Query[("Query")] --> Recall[("Recall")]
        Local -.->|Fast Recall| Recall
        Vector -.->|Semantic Search| Recall
        Recall --> Context[("Context Window")]
    end
    
    subgraph Cleanup["Cleanup Policies"]
        Local -->|Age > {local_retention}| LocalClean[("Delete")]
        Vector -->|Importance < 0.3| VectorClean[("Delete")]
    end
    
    style DualMem fill:#4f46e5,color:#fff
    style Local fill:#059669,color:#fff
    style Vector fill:#7c3aed,color:#fff
    style Recall fill:#ea580c,color:#fff
```"""
    return diagram


# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 OpenClaw Agent Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .agent-card { transition: transform 0.2s; }
        .agent-card:hover { transform: translateY(-2px); }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .memory-flow-card { transition: all 0.3s; }
        .memory-flow-card:hover { box-shadow: 0 4px 20px rgba(79, 70, 229, 0.3); }
        @media (max-width: 768px) {
            .grid-cols-3 { grid-template-columns: 1fr; }
            .grid-cols-4 { grid-template-columns: 1fr 1fr; }
        }
    </style>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <!-- Header -->
    <header class="bg-gray-800 border-b border-gray-700 sticky top-0 z-50">
        <div class="container mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <i class="fa-solid fa-robot text-2xl text-blue-400"></i>
                    <h1 class="text-xl font-bold">OpenClaw Dashboard</h1>
                </div>
                <div class="flex items-center space-x-4">
                    <span id="gateway-status" class="text-sm">
                        <i class="fa-solid fa-circle text-xs"></i> Gateway
                    </span>
                    <button onclick="refreshData()" class="bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded text-sm">
                        <i class="fa-solid fa-refresh"></i>
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- System Metrics -->
    <div class="bg-gray-800 border-b border-gray-700">
        <div class="container mx-auto px-4 py-3">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="text-center">
                    <div class="text-2xl font-bold text-blue-400" id="cpu">{{ metrics.cpu_percent }}%</div>
                    <div class="text-xs text-gray-400">CPU</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-green-400">{{ metrics.memory_percent }}%</div>
                    <div class="text-xs text-gray-400">RAM ({{ metrics.memory_used_gb }}/{{ metrics.memory_total_gb }}GB)</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-purple-400">{{ metrics.disk_percent }}%</div>
                    <div class="text-xs text-gray-400">Disk ({{ metrics.disk_used_gb }}/{{ metrics.disk_total_gb }}GB)</div>
                </div>
                <div class="text-center">
                    <div class="text-2xl font-bold text-yellow-400">{{ agents|length }}</div>
                    <div class="text-xs text-gray-400">Agents</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <main class="container mx-auto px-4 py-6">
        <h2 class="text-lg font-semibold mb-4">
            <i class="fa-solid fa-users mr-2"></i>Agents
        </h2>
        
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {% for agent in agents_data %}
            <div class="agent-card bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center space-x-2">
                        <div class="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                            <i class="fa-solid fa-robot"></i>
                        </div>
                        <div>
                            <h3 class="font-bold">{{ agent.name }}</h3>
                            <span class="text-xs text-gray-400">{{ agent.id }}</span>
                        </div>
                    </div>
                    <span class="px-2 py-1 rounded text-xs font-medium {% if agent.status == 'active' %}bg-green-900 text-green-300{% else %}bg-gray-700 text-gray-400{% endif %}">
                        {% if agent.status == 'active' %}<i class="fa-solid fa-circle text-xs pulse"></i>{% endif %}
                        {{ agent.status }}
                    </span>
                </div>
                
                <div class="grid grid-cols-2 gap-2 text-sm">
                    <div class="bg-gray-700 rounded p-2">
                        <div class="text-gray-400 text-xs">Sessions</div>
                        <div class="font-semibold">{{ agent.sessions }}</div>
                    </div>
                    <div class="bg-gray-700 rounded p-2">
                        <div class="text-gray-400 text-xs">Memory Files</div>
                        <div class="font-semibold">{{ agent.memory_files }}</div>
                    </div>
                    <div class="bg-gray-700 rounded p-2">
                        <div class="text-gray-400 text-xs">Config Files</div>
                        <div class="font-semibold">{{ agent.config_files }}/4</div>
                    </div>
                    <div class="bg-gray-700 rounded p-2">
                        <div class="text-gray-400 text-xs">Workspace</div>
                        <div class="font-semibold {% if agent.has_workspace %}text-green-400{% else %}text-red-400{% endif %}">
                            {% if agent.has_workspace %}<i class="fa-solid fa-check"></i>{% else %}<i class="fa-solid fa-xmark"></i>{% endif %}
                        </div>
                    </div>
                </div>
                
                {% if agent.last_active %}
                <div class="mt-3 text-xs text-gray-500">
                    Last active: {{ agent.last_active[:19] if agent.last_active else 'N/A' }}
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        <!-- Memory Flow Diagrams Section -->
        <div class="mt-8">
            <h2 class="text-lg font-semibold mb-4">
                <i class="fa-solid fa-memory mr-2 text-purple-400"></i>Memory Flow Diagrams
            </h2>
            
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {% for agent_id, config in memory_configs.items() %}
                <div class="memory-flow-card bg-gray-800 rounded-lg p-4 border border-gray-700">
                    <div class="flex items-center justify-between mb-3">
                        <h3 class="font-bold text-lg">
                            <i class="fa-solid fa-robot text-blue-400 mr-2"></i>{{ config.name }}
                        </h3>
                        <span class="text-xs text-gray-400">{{ agent_id }}</span>
                    </div>
                    
                    <!-- Role -->
                    <div class="mb-4 p-2 bg-gray-700/50 rounded text-sm">
                        <span class="text-gray-400">Role:</span> {{ config.role }}
                    </div>
                    
                    <!-- Storage Info -->
                    <div class="grid grid-cols-2 gap-3 mb-4">
                        <div class="bg-green-900/30 border border-green-700 rounded p-3">
                            <div class="text-green-400 text-xs font-semibold mb-1">
                                <i class="fa-solid fa-file-lines mr-1"></i>Local Storage
                            </div>
                            <div class="text-sm">
                                <div class="text-gray-400">Retention:</div>
                                <div>{{ config.local_storage.retention }}</div>
                            </div>
                        </div>
                        <div class="bg-purple-900/30 border border-purple-700 rounded p-3">
                            <div class="text-purple-400 text-xs font-semibold mb-1">
                                <i class="fa-solid fa-database mr-1"></i>Vector DB
                            </div>
                            <div class="text-sm">
                                <div class="text-gray-400">Retention:</div>
                                <div>{{ config.vector_db.retention }}</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Efficiency Parameters -->
                    <div class="mb-4">
                        <div class="text-xs text-gray-400 mb-2">Efficiency Parameters</div>
                        <div class="grid grid-cols-3 gap-2 text-center">
                            <div class="bg-gray-700 rounded p-2">
                                <div class="text-blue-400 font-bold">{{ config.efficiency.max_tokens_per_context }}</div>
                                <div class="text-xs text-gray-400">Max Tokens</div>
                            </div>
                            <div class="bg-gray-700 rounded p-2">
                                <div class="text-green-400 font-bold">{{ config.efficiency.target_recall_speed_ms }}ms</div>
                                <div class="text-xs text-gray-400">Recall Speed</div>
                            </div>
                            <div class="bg-gray-700 rounded p-2">
                                <div class="text-yellow-400 font-bold">{{ config.efficiency.storage_limit_mb }}MB</div>
                                <div class="text-xs text-gray-400">Storage Limit</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Mermaid Diagram -->
                    <div class="mt-4 p-3 bg-gray-900 rounded">
                        <div class="text-xs text-gray-400 mb-2">Data Flow Diagram</div>
                        <div class="mermaid" id="flow-{{ agent_id }}">
                            {{ memory_flows[agent_id] }}
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <!-- Agent List Summary -->
        <div class="mt-8 bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 class="font-semibold mb-3"><i class="fa-solid fa-list mr-2"></i>Agent Directory</h3>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="text-left text-gray-400 border-b border-gray-700">
                            <th class="pb-2">Agent ID</th>
                            <th class="pb-2">Status</th>
                            <th class="pb-2">Sessions</th>
                            <th class="pb-2">Workspace</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for agent in agents_data %}
                        <tr class="border-b border-gray-700/50">
                            <td class="py-2 font-mono">{{ agent.id }}</td>
                            <td class="py-2">
                                <span class="{% if agent.status == 'active' %}text-green-400{% else %}text-gray-400{% endif %}">
                                    {{ agent.status }}
                                </span>
                            </td>
                            <td class="py-2">{{ agent.sessions }}</td>
                            <td class="py-2">
                                {% if agent.has_workspace %}<i class="fa-solid fa-check text-green-400"></i>{% else %}<i class="fa-solid fa-xmark text-red-400"></i>{% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Quick Actions -->
        <div class="mt-8 bg-gray-800 rounded-lg p-4 border border-gray-700">
            <h3 class="font-semibold mb-3"><i class="fa-solid fa-bolt mr-2"></i>Quick Actions</h3>
            <div class="flex flex-wrap gap-2">
                <a href="/api/agents" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
                    <i class="fa-solid fa-code mr-1"></i>API: Agents
                </a>
                <a href="/api/metrics" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded text-sm">
                    <i class="fa-solid fa-chart-line mr-1"></i>API: Metrics
                </a>
                <a href="/api/memory" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded text-sm">
                    <i class="fa-solid fa-memory mr-1"></i>API: Memory
                </a>
                <button onclick="testApis()" class="bg-orange-600 hover:bg-orange-700 px-4 py-2 rounded text-sm">
                    <i class="fa-solid fa-plug mr-1"></i>Test APIs
                </button>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="mt-8 text-center text-gray-500 text-sm">
            <p>OpenClaw Agent Dashboard • Last updated: <span id="last-updated"></span></p>
            <p class="mt-1">Access from: {{ local_ip }}</p>
        </div>
    </main>

    <script>
        // Initialize Mermaid
        mermaid.initialize({ 
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose'
        });
        
        function refreshData() {
            location.reload();
        }
        
        function testApis() {
            fetch('/api/agents')
                .then(r => r.json())
                .then(d => console.log('Agents:', d));
            fetch('/api/metrics')
                .then(r => r.json())
                .then(d => console.log('Metrics:', d));
            fetch('/api/memory')
                .then(r => r.json())
                .then(d => console.log('Memory:', d));
            alert('Check console for API responses');
        }
        
        // Update timestamp
        document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
        
        // Gateway status
        fetch('/api/gateway')
            .then(r => r.json())
            .then(d => {
                const el = document.getElementById('gateway-status');
                if (d.status === 'online') {
                    el.innerHTML = '<i class="fa-solid fa-circle text-xs text-green-400"></i> Gateway: online';
                } else {
                    el.innerHTML = '<i class="fa-solid fa-circle text-xs text-red-400"></i> Gateway: offline';
                }
            })
            .catch(() => {
                document.getElementById('gateway-status').innerHTML = '<i class="fa-solid fa-circle text-xs text-red-400"></i> Gateway: offline';
            });
    </script>
</body>
</html>
"""


def get_local_ip():
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


@app.route("/")
def index():
    """Main dashboard page."""
    agents = get_all_agents()
    agents_data = [get_agent_status(a) for a in agents]
    metrics = get_system_metrics()
    local_ip = get_local_ip()
    
    # Generate memory configs and flows for known agents
    memory_configs = {}
    memory_flows = {}
    
    for agent_id in ["zjuniorcoder", "zseniorcoder", "zpredictor", "zhypetrader"]:
        if agent_id in AGENT_MEMORY_CONFIG:
            memory_configs[agent_id] = AGENT_MEMORY_CONFIG[agent_id]
            memory_flows[agent_id] = generate_mermaid_flow(agent_id)
    
    return render_template_string(
        DASHBOARD_HTML,
        agents=agents,
        agents_data=agents_data,
        metrics=metrics,
        local_ip=local_ip,
        memory_configs=memory_configs,
        memory_flows=memory_flows
    )


@app.route("/api/agents")
def api_agents():
    """API endpoint for agents."""
    agents = get_all_agents()
    return jsonify([get_agent_status(a) for a in agents])


@app.route("/api/metrics")
def api_metrics():
    """API endpoint for system metrics."""
    return jsonify(get_system_metrics())


@app.route("/api/gateway")
def api_gateway():
    """API endpoint for gateway status."""
    return jsonify({"status": get_gateway_status()})


@app.route("/api/memory")
def api_memory():
    """API endpoint for memory data."""
    result = {}
    for agent_id in AGENT_MEMORY_CONFIG.keys():
        result[agent_id] = get_memory_flow_data(agent_id)
    return jsonify(result)


@app.route("/api/memory/<agent_id>")
def api_memory_agent(agent_id):
    """API endpoint for specific agent memory data."""
    return jsonify(get_memory_flow_data(agent_id))


@app.route("/api/memory-flow/<agent_id>")
def api_memory_flow(agent_id):
    """API endpoint for memory flow diagram."""
    return jsonify({
        "agent_id": agent_id,
        "mermaid": generate_mermaid_flow(agent_id)
    })


if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║          🤖 OpenClaw Agent Dashboard                     ║
╠═══════════════════════════════════════════════════════════╣
║  Local:   http://localhost:5000                          ║
║  Network: http://{local_ip}:5000                         ║
║                                                           ║
║  Features:                                               ║
║  - Agent status monitoring                               ║
║  - System metrics (CPU, RAM, Disk)                       ║
║  - Memory flow diagrams per agent                        ║
║  - Dual memory system visualization (v3 + Qdrant)       ║
║                                                           ║
║  API Endpoints:                                          ║
║  - /api/agents       - All agent status                  ║
║  - /api/metrics      - System metrics                    ║
║  - /api/memory       - Memory data for all agents        ║
║  - /api/memory/<id>  - Memory data for specific agent    ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Run on all interfaces so it's accessible from network
    app.run(host="0.0.0.0", port=5000, debug=False)


# Export functions for testing
__all__ = [
    'get_agent_status',
    'get_all_agents', 
    'get_system_metrics',
    'get_gateway_status',
    'get_memory_flow_data',
    'generate_mermaid_flow',
    'AGENT_MEMORY_CONFIG'
]
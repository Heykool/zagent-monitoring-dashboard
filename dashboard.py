#!/usr/bin/env python3
"""
Agent Dashboard - Local monitoring for OpenClaw agents
Run: python3 dashboard.py
Access: http://localhost:5000 or http://<your-ip>:5000
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
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .agent-card { transition: transform 0.2s; }
        .agent-card:hover { transform: translateY(-2px); }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
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
                <button onclick="testApis()" class="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded text-sm">
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
    
    return render_template_string(
        DASHBOARD_HTML,
        agents=agents,
        agents_data=agents_data,
        metrics=metrics,
        local_ip=local_ip
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


if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║          🤖 OpenClaw Agent Dashboard                     ║
╠═══════════════════════════════════════════════════════════╣
║  Local:   http://localhost:5000                          ║
║  Network: http://{local_ip}:5000                         ║
║                                                           ║
║  Access from phone:                                       ║
║  1. Make sure phone is on same WiFi                     ║
║  2. Open browser and go to http://{local_ip}:5000       ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Run on all interfaces so it's accessible from network
    app.run(host="0.0.0.0", port=5000, debug=False)

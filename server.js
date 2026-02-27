const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execSync, spawnSync } = require('child_process');

const app = express();
const HOST = process.env.HOST || '0.0.0.0';
const PORT = process.env.PORT || 4780;
const AGENTS_DIR = process.env.OPENCLAW_AGENTS_DIR || '/root/.openclaw/agents';
const WORKSPACES_DIR = process.env.OPENCLAW_WORKSPACES_DIR || '/root/.openclaw';
const INPUT_COST_PER_M = Number(process.env.INPUT_COST_PER_M || 0.5);
const OUTPUT_COST_PER_M = Number(process.env.OUTPUT_COST_PER_M || 1.5);
const lastRefreshAt = new Map();

app.use((req,res,next)=>{res.setHeader('Cache-Control','no-store'); next();});
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

const readJson = (p, fb = null) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fb; } };
const readText = (p, fb = '') => { try { return fs.readFileSync(p, 'utf8'); } catch { return fb; } };

function getGateway() {
  try {
    const out = execSync('openclaw gateway status', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    const status = /Runtime:\s+running/i.test(out) ? 'online' : 'degraded';
    return { status, raw: out, latencyMs: null };
  } catch {
    return { status: 'offline', raw: 'gateway status unavailable', latencyMs: null };
  }
}

function getHost() {
  const total = os.totalmem();
  const free = os.freemem();
  const used = total - free;

  let disk = { percent: 0, totalHuman: 'n/a', usedHuman: 'n/a', freeHuman: 'n/a' };
  try {
    const df = execSync("df -k / | tail -1", { encoding: 'utf8' }).trim().split(/\s+/);
    const totalB = Number(df[1]) * 1024;
    const usedB = Number(df[2]) * 1024;
    const freeB = Number(df[3]) * 1024;
    disk = {
      percent: Math.round((usedB / totalB) * 100),
      totalHuman: `${Math.round(totalB / 1024 / 1024 / 1024)} GB`,
      usedHuman: `${Math.round(usedB / 1024 / 1024 / 1024)} GB`,
      freeHuman: `${Math.round(freeB / 1024 / 1024 / 1024)} GB`,
    };
  } catch {}

  return {
    hostname: os.hostname(),
    platform: os.platform(),
    arch: os.arch(),
    uptime: os.uptime(),
    cpuCount: os.cpus().length,
    cpuModel: os.cpus()[0]?.model || 'Unknown',
    cpuPercent: null,
    load: { '1m': os.loadavg()[0].toFixed(2), '5m': os.loadavg()[1].toFixed(2), '15m': os.loadavg()[2].toFixed(2) },
    memory: {
      total, used, free,
      percent: Math.round((used / total) * 100),
      totalHuman: `${(total / 1024 / 1024 / 1024).toFixed(2)} GB`,
      usedHuman: `${(used / 1024 / 1024 / 1024).toFixed(2)} GB`,
      freeHuman: `${(free / 1024 / 1024 / 1024).toFixed(2)} GB`,
    },
    disk,
  };
}

function getMemoryFiles(agentId, limit = 12) {
  const memDir = path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'memory');
  if (!fs.existsSync(memDir)) return [];
  return fs.readdirSync(memDir)
    .filter((f) => f.endsWith('.md'))
    .map((f) => ({ file: f, p: path.join(memDir, f), mtime: fs.statSync(path.join(memDir, f)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, limit)
    .map((x) => ({ file: x.file, mtime: x.mtime, content: readText(x.p, '') })); // full text
}



function getZhypeReport(agentId) {
  if (agentId !== 'zhypetrader') return null;
  const p = path.join(WORKSPACES_DIR, 'workspace-zhypetrader', 'logs', 'zhype_trading_report.json');
  return readJson(p, null);
}

function getPredictorReport(agentId) {
  if (agentId !== 'zpredictor') return null;
  const base = path.join(WORKSPACES_DIR, 'workspace-zpredictor', 'logs');
  const jsonPath = path.join(base, 'zpredictor_comprehensive_report.json');
  const mdPath = path.join(base, 'zpredictor_comprehensive_report.md');
  const report = readJson(jsonPath, null);
  if (!report) return null;
  return {
    ...report,
    markdown: readText(mdPath, ''),
  };
}


function getMemoryFrameworkStatus(agentId) {
  const ws = path.join(WORKSPACES_DIR, `workspace-${agentId}`);
  const memMcp = path.join(ws, 'memory-mcp', 'memory_server.py');
  const sem = path.join(ws, 'semantic_memory.py');
  const memDir = path.join(ws, 'memory');
  let latestMemoryFile = null;
  let latestMemoryMtime = null;
  if (fs.existsSync(memDir)) {
    const files = fs.readdirSync(memDir).filter(f=>f.endsWith('.md')).map(f=>({f, t: fs.statSync(path.join(memDir,f)).mtimeMs})).sort((a,b)=>b.t-a.t);
    if (files.length) { latestMemoryFile = files[0].f; latestMemoryMtime = files[0].t; }
  }
  return {
    hasMemoryMcp: fs.existsSync(memMcp),
    hasSemanticWrapper: fs.existsSync(sem),
    latestMemoryFile,
    latestMemoryMtime,
  };
}

function parseAgent(agentId) {
  const sessionsMap = readJson(path.join(AGENTS_DIR, agentId, 'sessions', 'sessions.json'), {}) || {};
  const entries = Object.entries(sessionsMap);
  const now = Date.now();
  const activeWindow = 60 * 60 * 1000;

  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let activeSessions = 0;
  let lastActivity = 0;

  const sessions = entries.map(([k, v]) => {
    const inputTokens = Number(v?.inputTokens || 0);
    const outputTokens = Number(v?.outputTokens || 0);
    const updatedAt = Number(v?.updatedAt || 0);
    totalInputTokens += inputTokens;
    totalOutputTokens += outputTokens;
    if (updatedAt > now - activeWindow) activeSessions += 1;
    if (updatedAt > lastActivity) lastActivity = updatedAt;
    return {
      id: v?.sessionId || k,
      status: updatedAt > now - activeWindow ? 'active' : 'idle',
      inputTokens,
      outputTokens,
      model: v?.model || null,
      createdAt: null,
      updatedAt: updatedAt || null,
    };
  }).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0)).slice(0, 30);

  const totalTokens = totalInputTokens + totalOutputTokens;
  const estimatedCost = ((totalInputTokens / 1_000_000) * INPUT_COST_PER_M) + ((totalOutputTokens / 1_000_000) * OUTPUT_COST_PER_M);

  return {
    id: agentId,
    name: agentId,
    description: null,
    status: activeSessions > 0 ? 'active' : 'idle',
    sessionCount: entries.length,
    activeSessions,
    totalInputTokens,
    totalOutputTokens,
    totalTokens,
    estimatedCost,
    lastActivity: lastActivity || null,
    sessions,
    memory: getMemoryFiles(agentId, 12), // full content
    predictorReport: getPredictorReport(agentId),
    zhypeReport: getZhypeReport(agentId),
    memoryFramework: getMemoryFrameworkStatus(agentId),
    configs: {
      SKILL: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'SKILL.md'), ''),
      SOUL: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'SOUL.md'), ''),
      AGENTS: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'AGENTS.md'), ''),
      MEMORY: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'MEMORY.md'), ''),
    }, // full text
  };
}

function parseAllAgents() {
  if (!fs.existsSync(AGENTS_DIR)) return [];
  return fs.readdirSync(AGENTS_DIR)
    .filter((d) => { try { return fs.statSync(path.join(AGENTS_DIR, d)).isDirectory(); } catch { return false; } })
    .map(parseAgent)
    .sort((a, b) => (b.lastActivity || 0) - (a.lastActivity || 0));
}


app.post('/api/refresh-trading', (req, res) => {
  const agent = (req.query.agent || req.body?.agent || '').toString().trim();
  if (!agent) return res.status(400).json({ error: 'agent is required' });
  if (!['zpredictor','zhypetrader'].includes(agent)) return res.status(400).json({ error: 'unsupported agent' });

  const now = Date.now();
  const last = lastRefreshAt.get(agent) || 0;
  const cooldownMs = 20000;
  if (now - last < cooldownMs) {
    return res.status(429).json({ error: 'cooldown', retryInSec: Math.ceil((cooldownMs - (now-last))/1000) });
  }

  let cmd = null;
  if (agent === 'zpredictor') {
    cmd = 'cd /root/.openclaw/workspace-zpredictor && AUTO_EXECUTE=false python3 reports/generate_comprehensive_report.py';
  } else if (agent === 'zhypetrader') {
    cmd = 'cd /root/.openclaw/workspace-zhypetrader && python3 reports/generate_hype_dashboard_report.py';
  }

  const r = spawnSync('/usr/bin/bash', ['-lc', cmd], { encoding: 'utf8', timeout: 120000 });
  if (r.status !== 0) {
    return res.status(500).json({ ok: false, status: r.status, stderr: (r.stderr || '').slice(0, 800), stdout: (r.stdout || '').slice(0, 800) });
  }
  lastRefreshAt.set(agent, now);
  return res.json({ ok: true, agent, refreshedAt: now, stdout: (r.stdout || '').trim().slice(0, 500) });
});

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString(), uptime: process.uptime() });
});

app.get('/api/overview', (_req, res) => {
  const fullAgents = parseAllAgents();
  const summary = {
    agentCount: fullAgents.length,
    activeAgents: fullAgents.filter((a) => a.status === 'active').length,
    totalSessions: fullAgents.reduce((s, a) => s + a.sessionCount, 0),
    totalActiveSessions: fullAgents.reduce((s, a) => s + a.activeSessions, 0),
    totalTokens: fullAgents.reduce((s, a) => s + a.totalTokens, 0),
    totalInputTokens: fullAgents.reduce((s, a) => s + a.totalInputTokens, 0),
    totalOutputTokens: fullAgents.reduce((s, a) => s + a.totalOutputTokens, 0),
    estimatedCostUSD: fullAgents.reduce((s, a) => s + (a.estimatedCost || 0), 0),
  };

  const agents = fullAgents.map((a) => ({
    id: a.id,
    name: a.name,
    description: a.description,
    status: a.status,
    sessionCount: a.sessionCount,
    activeSessions: a.activeSessions,
    totalInputTokens: a.totalInputTokens,
    totalOutputTokens: a.totalOutputTokens,
    totalTokens: a.totalTokens,
    estimatedCost: a.estimatedCost,
    lastActivity: a.lastActivity,
    // keep lightweight but include predictor payload for drawer fallback
    predictorReport: a.id === 'zpredictor' ? a.predictorReport : null,
    zhypeReport: a.id === 'zhypetrader' ? a.zhypeReport : null,
    memoryFramework: a.id === 'zpredictor' ? a.memoryFramework : null,
    sessions: (a.sessions || []).slice(0, 3),
  }));

  res.json({ timestamp: new Date().toISOString(), summary, gateway: getGateway(), host: getHost(), agents });
});

app.get('/api/agents/:id', (req, res) => {
  const agent = parseAgent(req.params.id);
  if (!agent) return res.status(404).json({ error: 'Agent not found' });
  res.json(agent);
});

app.listen(PORT, HOST, () => {
  console.log(`Agent Watch Dashboard running on http://${HOST}:${PORT}`);
});

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
const TASKS_FILE = path.join(__dirname, 'tasks.json');

function loadTasks() {
  const payload = readJson(TASKS_FILE, { tasks: [] });
  const list = Array.isArray(payload?.tasks) ? payload.tasks : [];
  const allowed = new Set(['backlog', 'in_progress', 'review', 'done']);
  const norm = [];
  for (const t of list) {
    if (!t || typeof t !== 'object') continue;
    if (!t.id || !t.title) continue;
    const status = allowed.has(String(t.status || '').toLowerCase()) ? String(t.status).toLowerCase() : 'backlog';
    norm.push({
      id: String(t.id),
      title: String(t.title),
      status,
      assignees: Array.isArray(t.assignees) ? t.assignees : [],
      date_assigned: t.date_assigned || null,
      date_completed: t.date_completed || null,
      description: t.description || '',
      decisions: Array.isArray(t.decisions) ? t.decisions : [],
      subtasks: Array.isArray(t.subtasks) ? t.subtasks : [],
      links: Array.isArray(t.links) ? t.links : [],
    });
  }
  norm.sort((a, b) => String(b.date_assigned || '').localeCompare(String(a.date_assigned || '')));
  return norm;
}

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
    disk = { percent: Math.round((usedB / totalB) * 100), totalHuman: `${Math.round(totalB/1024/1024/1024)} GB`, usedHuman: `${Math.round(usedB/1024/1024/1024)} GB`, freeHuman: `${Math.round((totalB-usedB)/1024/1024/1024)} GB` };
  } catch {}
  return { hostname: os.hostname(), platform: os.platform(), arch: os.arch(), uptime: os.uptime(), cpuCount: os.cpus().length, cpuModel: os.cpus()[0]?.model||'Unknown', cpuPercent: null, load: { '1m': os.loadavg()[0].toFixed(2), '5m': os.loadavg()[1].toFixed(2), '15m': os.loadavg()[2].toFixed(2) }, memory: { total, used, free, percent: Math.round((used/total)*100), totalHuman: `${(total/1024/1024/1024).toFixed(2)} GB`, usedHuman: `${(used/1024/1024/1024).toFixed(2)} GB`, freeHuman: `${(free/1024/1024/1024).toFixed(2)} GB` }, disk };
}

function getMemoryFiles(agentId, limit = 12) {
  const memDir = path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'memory');
  if (!fs.existsSync(memDir)) return [];
  return fs.readdirSync(memDir).filter((f) => f.endsWith('.md')).map((f) => ({ file: f, p: path.join(memDir, f), mtime: fs.statSync(path.join(memDir, f)).mtimeMs })).sort((a, b) => b.mtime - a.mtime).slice(0, limit).map((x) => ({ file: x.file, mtime: x.mtime, content: readText(x.p, '') }));
}

function tailLines(filePath, lines = 120) { try { return execSync(`tail -n ${Number(lines)} ${JSON.stringify(filePath)}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }); } catch { return ''; } }
function compact(s, max = 160) { const t = String(s || '').replace(/\s+/g, ' ').trim(); return t.length > max ? `${t.slice(0, max - 1)}…` : t; }

function summarizeContent(content) {
  if (!Array.isArray(content) || !content.length) return '';
  const textPart = content.find((c) => c?.type === 'text' && c?.text);
  if (textPart?.text) return compact(textPart.text, 180);
  const toolPart = content.find((c) => c?.type === 'toolCall' && c?.name);
  if (toolPart?.name) return `tool:${toolPart.name}`;
  const toolResultPart = content.find((c) => c?.type === 'toolResult' && c?.toolName);
  if (toolResultPart?.toolName) return `toolResult:${toolResultPart.toolName}`;
  return compact(JSON.stringify(content[0] || ''), 180);
}

function getAgentActions(agentId, sessionsMap, limit = 30) {
  const actions = [], entries = Object.values(sessionsMap || {}).slice(0, 40);
  for (const s of entries) {
    const sessionId = s?.sessionId, sessionFile = s?.sessionFile;
    if (!sessionId || !sessionFile || !fs.existsSync(sessionFile)) continue;
    const raw = tailLines(sessionFile, 120);
    if (!raw) continue;
    const lines = raw.split('\n').filter(Boolean);
    for (const line of lines) {
      try {
        const obj = JSON.parse(line);
        if (obj?.type !== 'message') continue;
        const msg = obj?.message || {}, role = msg?.role || 'unknown', ts = obj?.timestamp || null, summary = summarizeContent(msg?.content);
        if (!summary) continue;
        actions.push({ ts, role, sessionId, summary });
      } catch {}
    }
  }
  return actions.filter((a) => !!a.ts).sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()).slice(0, limit);
}

function getZoptionReport(agentId) { if (agentId !== 'zoption1mintrader') return null; return readJson(path.join(WORKSPACES_DIR, 'workspace-zoption1mintrader', 'logs', 'zoption1min_report.json'), null); }
function getZhypeReport(agentId) { if (agentId !== 'zhypetrader') return null; return readJson(path.join(WORKSPACES_DIR, 'workspace-zhypetrader', 'logs', 'zhype_trading_report.json'), null); }
function getPredictorReport(agentId) {
  if (agentId !== 'zpredictor') return null;
  const base = path.join(WORKSPACES_DIR, 'workspace-zpredictor', 'logs');
  const jsonPath = path.join(base, 'zpredictor_comprehensive_report.json'), mdPath = path.join(base, 'zpredictor_comprehensive_report.md');
  const report = readJson(jsonPath, null);
  if (!report) return null;
  return { ...report, markdown: readText(mdPath, '') };
}

function getMemoryFrameworkStatus(agentId) {
  const ws = path.join(WORKSPACES_DIR, `workspace-${agentId}`), memMcp = path.join(ws, 'memory-mcp', 'memory_server.py'), sem = path.join(ws, 'semantic_memory.py'), memDir = path.join(ws, 'memory');
  let latestMemoryFile = null, latestMemoryMtime = null;
  if (fs.existsSync(memDir)) {
    const files = fs.readdirSync(memDir).filter(f=>f.endsWith('.md')).map(f=>({f, t: fs.statSync(path.join(memDir,f)).mtimeMs})).sort((a,b)=>b.t-a.t);
    if (files.length) { latestMemoryFile = files[0].f; latestMemoryMtime = files[0].t; }
  }
  return { hasMemoryMcp: fs.existsSync(memMcp), hasSemanticWrapper: fs.existsSync(sem), latestMemoryFile, latestMemoryMtime };
}

// Memory flow configuration per agent
const AGENT_MEMORY_CONFIG = {
  zjuniorcoder: { local: { path: 'memory/', files: ['MEMORY.md', 'MEMORY_BRIEFING.md'], retention: 7, maxSize: '50MB' }, vector: { db: 'Qdrant', collection: 'zjuniorcoder_memories', dimensions: 1536, retention: 30 }, dual: { enabled: true, syncInterval: '5min', tier: 'episodic' }, efficiency: { maxTokens: 8000, recallSpeed: '150ms', storageLimit: '50MB' } },
  zseniorcoder: { local: { path: 'memory/', files: ['MEMORY.md'], retention: 14, maxSize: '100MB' }, vector: { db: 'Qdrant', collection: 'zseniorcoder_memories', dimensions: 1536, retention: 60 }, dual: { enabled: true, syncInterval: '10min', tier: 'semantic' }, efficiency: { maxTokens: 12000, recallSpeed: '200ms', storageLimit: '100MB' } },
  zpredictor: { local: { path: 'memory/', files: ['MEMORY.md', 'daily-*.md'], retention: 3, maxSize: '200MB' }, vector: { db: 'Qdrant', collection: 'zpredictor_memories', dimensions: 1536, retention: 14 }, dual: { enabled: true, syncInterval: '3min', tier: 'episodic' }, efficiency: { maxTokens: 6000, recallSpeed: '100ms', storageLimit: '200MB' } },
  zhypetrader: { local: { path: 'memory/', files: ['MEMORY.md'], retention: 1, maxSize: '500MB' }, vector: { db: 'Qdrant', collection: 'zhypetrader_memories', dimensions: 1536, retention: 7 }, dual: { enabled: true, syncInterval: '1min', tier: 'episodic' }, efficiency: { maxTokens: 4000, recallSpeed: '50ms', storageLimit: '500MB' } }
};

function getMemoryFlow(agentId) {
  const config = AGENT_MEMORY_CONFIG[agentId];
  if (!config) return null;
  const ws = path.join(WORKSPACES_DIR, `workspace-${agentId}`), memDir = path.join(ws, 'memory');
  let totalSize = 0, fileCount = 0;
  if (fs.existsSync(memDir)) {
    const files = fs.readdirSync(memDir).filter(f => f.endsWith('.md'));
    fileCount = files.length;
    for (const f of files) { try { totalSize += fs.statSync(path.join(memDir, f)).size; } catch {} }
  }
  return { agentId, config, usage: { files: fileCount, sizeBytes: totalSize, sizeHuman: `${(totalSize/1024/1024).toFixed(2)} MB` }, flow: { input: 'User Input / Cron', stores: [ { name: 'Local Files', type: 'file', path: config.local.path, retention: config.local.retention }, { name: 'Vector DB', type: 'qdrant', collection: config.vector.collection, retention: config.vector.retention }, { name: 'Dual Memory', type: 'dual', syncInterval: config.dual.syncInterval, tier: config.dual.tier } ], output: 'Agent Context' } };
}

function parseAgent(agentId) {
  const sessionsMap = readJson(path.join(AGENTS_DIR, agentId, 'sessions', 'sessions.json'), {}) || {};
  const entries = Object.entries(sessionsMap);
  const now = Date.now(), activeWindow = 60 * 60 * 1000;
  let totalInputTokens = 0, totalOutputTokens = 0, activeSessions = 0, lastActivity = 0;
  const sessions = entries.map(([k, v]) => {
    const inputTokens = Number(v?.inputTokens || 0), outputTokens = Number(v?.outputTokens || 0), updatedAt = Number(v?.updatedAt || 0);
    totalInputTokens += inputTokens; totalOutputTokens += outputTokens;
    if (updatedAt > now - activeWindow) activeSessions += 1;
    if (updatedAt > lastActivity) lastActivity = updatedAt;
    return { id: v?.sessionId || k, status: updatedAt > now - activeWindow ? 'active' : 'idle', inputTokens, outputTokens, model: v?.model || null, createdAt: null, updatedAt: updatedAt || null };
  }).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0)).slice(0, 30);
  const totalTokens = totalInputTokens + totalOutputTokens;
  const estimatedCost = ((totalInputTokens / 1_000_000) * INPUT_COST_PER_M) + ((totalOutputTokens / 1_000_000) * OUTPUT_COST_PER_M);
  return { id: agentId, name: agentId, description: null, status: activeSessions > 0 ? 'active' : 'idle', sessionCount: entries.length, activeSessions, totalInputTokens, totalOutputTokens, totalTokens, estimatedCost, lastActivity: lastActivity || null, sessions, actions: getAgentActions(agentId, sessionsMap, 30), memory: getMemoryFiles(agentId, 12), memoryFlow: getMemoryFlow(agentId), predictorReport: getPredictorReport(agentId), zhypeReport: getZhypeReport(agentId), zoptionReport: getZoptionReport(agentId), memoryFramework: getMemoryFrameworkStatus(agentId), configs: { SKILL: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'SKILL.md'), ''), SOUL: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'SOUL.md'), ''), AGENTS: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'AGENTS.md'), ''), MEMORY: readText(path.join(WORKSPACES_DIR, `workspace-${agentId}`, 'MEMORY.md'), '') } };
}

function parseAllAgents() {
  const agentIds = new Set();
  if (fs.existsSync(AGENTS_DIR)) { fs.readdirSync(AGENTS_DIR).filter((d) => { try { return fs.statSync(path.join(AGENTS_DIR, d)).isDirectory(); } catch { return false; } }).forEach((d) => agentIds.add(d)); }
  if (fs.existsSync(WORKSPACES_DIR)) { fs.readdirSync(WORKSPACES_DIR).filter((d) => d.startsWith('workspace-')).forEach((d) => agentIds.add(d.replace(/^workspace-/, ''))); }
  return [...agentIds].map(parseAgent).sort((a, b) => (b.lastActivity || 0) - (a.lastActivity || 0));
}

app.post('/api/refresh-trading', (req, res) => {
  const agent = (req.query.agent || req.body?.agent || '').toString().trim();
  if (!agent) return res.status(400).json({ error: 'agent is required' });
  if (!['zpredictor','zhypetrader','zoption1mintrader'].includes(agent)) return res.status(400).json({ error: 'unsupported agent' });
  const now = Date.now(), last = lastRefreshAt.get(agent) || 0, cooldownMs = 20000;
  if (now - last < cooldownMs) return res.status(429).json({ error: 'cooldown', retryInSec: Math.ceil((cooldownMs - (now-last))/1000) });
  let cmd = null;
  if (agent === 'zpredictor') cmd = 'cd /root/.openclaw/workspace-zpredictor && AUTO_EXECUTE=false python3 reports/generate_comprehensive_report.py';
  else if (agent === 'zhypetrader') cmd = 'cd /root/.openclaw/workspace-zhypetrader && python3 reports/generate_hype_dashboard_report.py';
  else if (agent === 'zoption1mintrader') cmd = 'cd /root/.openclaw/workspace-zoption1mintrader && python3 reports/generate_option_dashboard_report.py';
  const r = spawnSync('/usr/bin/bash', ['-lc', cmd], { encoding: 'utf8', timeout: 120000 });
  if (r.status !== 0) return res.status(500).json({ ok: false, status: r.status, stderr: (r.stderr || '').slice(0, 800), stdout: (r.stdout || '').slice(0, 800) });
  lastRefreshAt.set(agent, now);
  return res.json({ ok: true, agent, refreshedAt: now, stdout: (r.stdout || '').trim().slice(0, 500) });
});

app.get('/api/health', (_req, res) => res.json({ status: 'ok', timestamp: new Date().toISOString(), uptime: process.uptime() }));

app.get('/api/memory-flow', (_req, res) => { const flows = {}; for (const agentId of Object.keys(AGENT_MEMORY_CONFIG)) { flows[agentId] = getMemoryFlow(agentId); } res.json({ timestamp: new Date().toISOString(), agents: flows }); });

app.get('/api/memory-flow/:id', (req, res) => { const flow = getMemoryFlow(req.params.id); if (!flow) return res.status(404).json({ error: 'No memory config for agent' }); res.json(flow); });

let _overviewCache = null, _overviewCacheAt = 0;
const OVERVIEW_CACHE_TTL = 30000;

app.get('/api/overview', (_req, res) => {
  const now = Date.now();
  if (_overviewCache && (now - _overviewCacheAt) < OVERVIEW_CACHE_TTL) {
    return res.json({ ..._overviewCache, timestamp: new Date().toISOString(), cached: true });
  }
  const fullAgents = parseAllAgents();
  const summary = { agentCount: fullAgents.length, activeAgents: fullAgents.filter((a) => a.status === 'active').length, totalSessions: fullAgents.reduce((s, a) => s + a.sessionCount, 0), totalActiveSessions: fullAgents.reduce((s, a) => s + a.activeSessions, 0), totalTokens: fullAgents.reduce((s, a) => s + a.totalTokens, 0), totalInputTokens: fullAgents.reduce((s, a) => s + a.totalInputTokens, 0), totalOutputTokens: fullAgents.reduce((s, a) => s + a.totalOutputTokens, 0), estimatedCostUSD: fullAgents.reduce((s, a) => s + (a.estimatedCost || 0), 0) };
  const agents = fullAgents.map((a) => ({ id: a.id, name: a.name, description: a.description, status: a.status, sessionCount: a.sessionCount, activeSessions: a.activeSessions, totalInputTokens: a.totalInputTokens, totalOutputTokens: a.totalOutputTokens, totalTokens: a.totalTokens, estimatedCost: a.estimatedCost, lastActivity: a.lastActivity, memoryFlow: a.memoryFlow, predictorReport: a.id === 'zpredictor' ? a.predictorReport : null, zhypeReport: a.id === 'zhypetrader' ? a.zhypeReport : null, zoptionReport: a.id === 'zoption1mintrader' ? a.zoptionReport : null, memoryFramework: a.memoryFramework, sessions: (a.sessions || []).slice(0, 3) }));
  const result = { summary, gateway: getGateway(), host: getHost(), agents };
  _overviewCache = result; _overviewCacheAt = Date.now();
  res.json({ ...result, timestamp: new Date().toISOString(), cached: false });
});

app.get('/api/agents/:id', (req, res) => { const agent = parseAgent(req.params.id); if (!agent) return res.status(404).json({ error: 'Agent not found' }); res.json(agent); });

app.get('/api/tasks', (_req, res) => {
  const grouped = { backlog: [], in_progress: [], review: [], done: [] };
  for (const t of loadTasks()) grouped[t.status].push(t);
  res.json(grouped);
});

app.get('/api/tasks/:id', (req, res) => {
  const task = loadTasks().find((t) => t.id === req.params.id);
  if (!task) return res.status(404).json({ error: 'Task not found' });
  res.json(task);
});

app.listen(PORT, HOST, () => { console.log(`Agent Watch Dashboard running on http://${HOST}:${PORT}`); });

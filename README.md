# Agent Watch Dashboard

Local dashboard to monitor all OpenClaw agents.

## Features
- Monitors all `/root/.openclaw/agents/*`
- Shows sessions, active sessions, total token usage
- Host metrics (RAM, load, disk)
- Gateway status
- Mobile-friendly UI

## Run
```bash
cd /root/.openclaw/workspace-zseniorcoder/agent-watch-dashboard
npm install
HOST=0.0.0.0 PORT=4780 npm start
```

Optional cost estimation env:
```bash
INPUT_COST_PER_M=2.5 OUTPUT_COST_PER_M=10 npm start
```

Open from phone/browser:
- `http://<your-host-ip>:4780`

## API
- `GET /api/overview`
- `GET /api/health`

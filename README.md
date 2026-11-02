# page-monitor-mcp-server

Deterministic web page change monitoring MCP server with SHA-256 snapshot evidence. Free single-page diff, no key required; 7x24 scheduled monitoring via a Cat1 API key from https://toplformater.click.

## What it does

- **Noise-filtered deterministic diff** (`cat1_diff_page`): compares a target web page (or local HTML) against a baseline, stripping dynamic noise -- `<script>`/`<style>`, random `nonce`/`request-id`, dynamic counters, relative timestamps, and JSON indentation differences -- and returns the normalized text's SHA-256 hashes, a structured change summary, and a unified diff. Free, no key, no account, no card.
- **SHA-256 cryptographic evidence chain**: every `cat1_diff_page` call records `baseline_sha256`, `target_sha256`, `diff_patch_sha256`, `structured_changes`, and `unified_diff`, so any result can be independently re-fetched and hash-verified. No hallucinated changes.
- **7x24 scheduled monitoring gate** (`cat1_schedule_monitor`): requests or validates a Cat1 API key for always-on scheduled monitoring. Without a key it returns directions to get one at https://toplformater.click (USD 29/month, 7-day free trial, no card required). With a key it only checks the key format locally (`^cat1_(?:live|trial)_[A-Za-z0-9]{16,64}$`); it never calls an external payment or verification endpoint, never fabricates a verification result, and never pretends to run the schedule locally. Actual 7x24 monitoring is performed by our own cloud service. The tool honestly reports `local_scheduler_started: false` and `online_verified: false`.

## Tools

| Tool | Key required | Purpose |
| --- | --- | --- |
| `cat1_diff_page` | No | Free single-page noise-filtered diff + SHA-256 evidence. Inputs: `target_url` (required), `baseline_source` (optional), `baseline_sha256` (optional). |
| `cat1_schedule_monitor` | Optional (gate) | Scheduled-monitoring key gate + directions. Inputs: `target_url` (required), `interval_minutes` (optional, default 15), `alert_email` (optional), `api_key` (optional, or `CAT1_API_KEY` env var). |

## Quickstart

### Requirements

- Python 3.9+ (standard library only, zero third-party dependencies), or Docker for the OCI image.

### Option A -- Run from source

```bash
git clone https://github.com/jhfg31410-ai/page-monitor-mcp-server.git
cd page-monitor-mcp-server
python3 server.py
```

### Option B -- Run with Docker (after the image is published)

```bash
docker run -i --rm ghcr.io/jhfg31410-ai/page-monitor-mcp-server:0.1.0
```

### Claude Desktop / Cursor configuration

Copy `claude_desktop_config.example.json` into your MCP client config and set the server path (or the Docker image). Example (source):

```json
{
  "mcpServers": {
    "page-monitor-mcp-server": {
      "command": "python3",
      "args": ["/path/to/page-monitor-mcp-server/server.py"],
      "env": {
        "CAT1_API_KEY": "YOUR_CAT1_KEY_HERE_OPTIONAL"
      }
    }
  }
}
```

## Pricing

- Single-page diff (`cat1_diff_page`): free, no key, no account, no card.
- 7x24 scheduled monitoring: USD 29/month, 7-day free trial, no card required. Get a formal API key at https://toplformater.click. All payments go through our own site (Paddle / PayPal); this server never handles payments.

## Files

- `server.py` -- MCP `stdio` server (implements `initialize`, `tools/list`, `tools/call`, and the key gate).
- `engine.py` -- noise-filtering and semantic diff core (SHA-256, structured diff).
- `server.json` -- Official MCP Registry descriptor (public repo and Docker image not yet created/published).
- `Dockerfile` -- OCI image build (Python 3.12-slim, zero dependencies).
- `requirements.txt` -- package list (zero third-party dependencies, Python >= 3.9 stdlib only).
- `claude_desktop_config.example.json` -- Claude Desktop / Cursor mount example (placeholder key only).
- `fixtures/t0_sample.html`, `fixtures/t1_sample.html` -- local diff test HTML snapshots.

## Local test commands

### List tools (`tools/list`)

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' | python3 server.py
```

### Free diff test (`cat1_diff_page`, no key)

```bash
printf '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"cat1_diff_page","arguments":{"baseline_source":"fixtures/t0_sample.html","target_url":"fixtures/t1_sample.html"}}}\n' | python3 server.py
```

### Key-gate test (`cat1_schedule_monitor`)

No key (returns directions):

```bash
printf '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"cat1_schedule_monitor","arguments":{"target_url":"https://news.ycombinator.com/","interval_minutes":5}}}\n' | python3 server.py
```

With a format-matching demo key (local format check only; no network verification, no local scheduling):

```bash
printf '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"cat1_schedule_monitor","arguments":{"target_url":"https://news.ycombinator.com/","interval_minutes":5,"api_key":"cat1_trial_DemoFormatCheckOnly9999"}}}\n' | python3 server.py
```

## Status

- Version `0.1.0`. Server name `page-monitor-mcp-server`.
- This repository is prepared for publication to the Official MCP Registry (`server.json` included) and for listing on Glama / PulseMCP. The public repository, Docker image, and registry submission are not yet published.
- License: MIT (see `LICENSE`).

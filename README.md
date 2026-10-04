# RPMC

RPMC is a Python implementation of the RAS administration workflow. It keeps the same 12-byte binary frame header and separates the agent, server, common protocol, and CustomTkinter console.

## Working features

- Authenticated local server, reconnecting agent, and console RPC.
- Live connected-agent list, optional 2-second system telemetry, and optional 2-second process inventory refresh.
- On-demand or 2-second live process inventory; termination is disabled on the agent unless explicitly enabled.
- Directory listing and file download, confined to the agent's configured root; files over 8 MiB are rejected.
- Persistent screen-stream connection with 64x64 JPEG delta tiles (up to about 8 frames/second when capture permits) and a remote stop/reset request.
- Persistent SHA-256 chained server audit log with integrity verification.
- Operations terminal for a fixed allowlist of RPMC requests; it is not an operating-system shell.

## Local demo (Windows PowerShell)

The demo is loopback-only and is intended for a single Windows machine. Use three PowerShell windows. In each window, go to the project folder:

```powershell
Set-Location 'C:\Users\Lenovo\OneDrive\Desktop\Finalproject\RPMC'
```

Install dependencies once and check Python:

```powershell
python --version
python -m pip install -r requirements.txt
```

Generate two separate random tokens in the server window. Copy each printed token into the matching variable in the agent and console windows. Keep these demo tokens local and do not commit them:

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$adminToken = [Convert]::ToBase64String($bytes)
$rng.GetBytes($bytes)
$agentToken = [Convert]::ToBase64String($bytes)
$rng.Dispose()
Write-Host "Console token: $adminToken"
Write-Host "Agent token:   $agentToken"
```

Server window:

```powershell
$env:RPMC_ADMIN_TOKEN = $adminToken
$env:RPMC_AGENT_TOKEN = $agentToken
python -m server.server_main
```

Agent window:

```powershell
$env:RPMC_AGENT_TOKEN = '<paste the Agent token printed by the server window>'
$env:RPMC_AGENT_ROOT = Join-Path $env:TEMP 'rpmc-agent-demo'
New-Item -ItemType Directory -Force -Path $env:RPMC_AGENT_ROOT | Out-Null
$env:RPMC_SERVER_HOST = '127.0.0.1'
$env:RPMC_SERVER_PORT = '8090'
$env:RPMC_CLIENT_ID = $env:COMPUTERNAME
python -m agent.agent_main
```

Console window:

```powershell
$env:RPMC_ADMIN_TOKEN = '<paste the Console token printed by the server window>'
$env:RPMC_SERVER_PORT = '8090'
python -m console.app
```

Replace each paste instruction with the matching full token value (do not include the angle brackets). In the console, click **Refresh Agents**, select the connected agent, then open Dashboard, Processes, Files, Screen Stream, SOC Terminal, or Audit Log. Use **Start Live Telemetry** and **Start Live** for their 2-second refresh loops. **Start Screen View** opens the continuous delta-tile stream; click **Stop** when finished.

To stop the demo, close the console window and press `Ctrl+C` in the server and agent windows. The agent can browse and download only files under `RPMC_AGENT_ROOT`; use a dedicated demo folder rather than the repository or your home directory.

## Security boundaries

- The server binds to `127.0.0.1` only. Non-loopback binding is rejected; this demo does not implement TLS or production remote deployment.
- The agent accesses only `RPMC_AGENT_ROOT` and descendants, and file downloads are limited to 8 MiB.
- Process termination requires both an explicit console confirmation and `RPMC_ALLOW_PROCESS_TERMINATION=1` in the agent environment. The agent additionally refuses protected PIDs and processes owned by another user.
- The console does not expose file upload, deletion, power actions, or arbitrary shell execution.
- The agent token authenticates agents to the local server; the console token authenticates administrative RPC. Use distinct random values.

## Protocol

The frame header is wire-compatible with the Java implementation:

- magic: `0x5352`
- version: `0x01`
- reserved: `0x00`
- payload length: 32-bit big-endian integer
- frame type: 16-bit enum
- command type: 16-bit enum

Frames are read to their declared length, including across partial TCP reads. The codec and command definitions are in `common/protocol.py`.

## Verification

Run the syntax checks and local client-server-agent integration tests from this directory:

```powershell
python -m compileall -q .
python -m unittest discover -v
```

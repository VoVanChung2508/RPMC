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

The frame header is wire-compatible with the binary TCP specification:

- magic: `0x5352`
- version: `0x01`
- reserved: `0x00`
- payload length: 32-bit big-endian integer
- frame type: 16-bit enum
- command type: 16-bit enum

Frames are read to their declared length, including across partial TCP reads. The codec and command definitions are in `common/protocol.py`.

---

# HỆ THỐNG GIÁM SÁT THI TRỰC TUYẾN QUA MẠNG LAN (SCRUM ARCHITECTURE)

Đề tài bài tập lớn môn **Lập trình mạng** - Hệ thống giám sát thi thời gian thực hoạt động qua mạng LAN sử dụng giao thức **TCP Socket thuần** kết hợp **HTTP/SSE**, vận hành theo quy trình **Scrum**.

## 1. Phân Quyền & Vai Trò Theo Quy Trình Scrum

- **Product Owner (PO) / Giảng viên**:
  - Giao diện Dashboard cấu hình quy chế thi: Thang điểm ban đầu (10.0), mức trừ điểm (-1.0 đ/lần vi phạm), giới hạn vi phạm tối đa (3 lần), thời gian thi.
  - Nghiệm thu kết quả: Bảng điểm tổng hợp cuối kỳ, xuất báo cáo CSV và trích xuất toàn bộ Audit Log vết vi phạm.
- **Scrum Master (SM) / Giám thị phòng thi**:
  - Giao diện Real-time LAN Monitoring: Lắng nghe danh sách thí sinh đang kết nối qua IP mạng LAN.
  - Hộp Live Alert Feed: Nhận cảnh báo đẩy tức thì (Push Alert) khi thí sinh vi phạm (`TAB_SWITCH`, `BLUR`, `EXIT_FULLSCREEN`).
  - Quyền can thiệp (Intervention): Gửi tin nhắn cảnh báo trực tiếp lên màn hình thí sinh, đánh dấu vi phạm thủ công, hoặc cưỡng chế khóa bài thi ngay lập tức.
- **Developers / Học sinh (Client)**:
  - Giao diện thi trắc nghiệm lập trình mạng (`web/`).
  - Tự động kích hoạt toàn màn hình (Fullscreen) và lắng nghe các sự kiện gian lận: `visibilitychange` (chuyển tab), `blur` (mất focus chuột), `fullscreenchange` (thoát toàn màn hình), phím tắt cấm (`F12`, `Alt+Tab`).
  - Hiển thị HUD điểm số thời gian thực và nhận cảnh báo trực tiếp từ Giám thị. Tự động bị khóa bài khi vượt quá số lần vi phạm.

## 2. Bảng Cấu Trúc Gói Tin TCP (TCP Framing Wire Format)

Khắc phục triệt để hiện tượng **dính gói / xé gói** (Packet Concatenation & Fragmentation) qua TCP Stream:

| Byte Offset | Độ dài | Tên trường | Kiểu dữ liệu (Struct) | Mô tả |
| :--- | :--- | :--- | :--- | :--- |
| `0 - 1` | 2 bytes | `MAGIC_HEADER` | `>H` (Unsigned Short) | `0x5352` ('SR') nhận diện gói tin hợp lệ |
| `2` | 1 byte | `PROTOCOL_VERSION` | `>B` (Unsigned Char) | `0x01` phiên bản giao thức |
| `3` | 1 byte | `RESERVED` | `>B` (Unsigned Char) | `0x00` dự phòng mở rộng |
| `4 - 7` | 4 bytes | `PAYLOAD_LENGTH` | `>I` (Unsigned Int BE) | Độ dài dữ liệu thân ($N$ bytes) |
| `8 - 9` | 2 bytes | `FRAME_TYPE` | `>H` (Unsigned Short) | `CONTROL (0x0001)`, `DATA (0x0002)` |
| `10 - 11` | 2 bytes | `COMMAND_TYPE` | `>H` (Unsigned Short) | `EXAM_VIOLATION_REPORT (0x0604)`, etc. |
| `12 -> 12+N` | $N$ bytes | `PAYLOAD` | UTF-8 JSON Bytes | Dữ liệu chi tiết sự kiện |

## 3. Sơ Đồ Luồng Truyền Tin (Sequence Diagram)

```
[Thí sinh / Developer]             [Server Lập Trình Mạng]             [Giám thị / Scrum Master]
        |                                     |                                    |
        |--- Đăng ký phòng thi (TCP/HTTP) --->|                                    |
        |<-- Phản hồi điểm 10.0 (TCP/HTTP) ---|--- [TCP Broadcast] Thí sinh mới -->|
        |                                     |                                    |
        |-- [Vi phạm: Chuyển Tab/F11] ------->|                                    |
        |                                     |-- Tính điểm: 10 - 1 = 9.0 đ        |
        |<-- Phản hồi cảnh báo đỏ (9.0 đ) ----|-- [TCP Push Alert] Bật chuông ---->|
        |                                     |                                    |
        |                                     |<-- [TCP] Gửi cảnh báo nhắc nhở ----|
        |<-- [Push] Nhận tin từ Giám thị -----|                                    |
```

## 4. Hướng Dẫn Cài Đặt & Kịch Bản Thử Nghiệm Mạng LAN

### Bước 1: Khởi động Server (Chạy cả TCP Socket và Web Server)
Mở PowerShell 1 tại thư mục dự án:
```powershell
$adminToken = "admin_secret_token_12345678"
$agentToken = "agent_secret_token_12345678"
$env:RPMC_ADMIN_TOKEN = $adminToken
$env:RPMC_AGENT_TOKEN = $agentToken
$env:RPMC_ALLOW_PRIVATE_NETWORK = "1"
$env:RPMC_BIND_HOST = "0.0.0.0"
python -m server.server_main
```
*Server sẽ lắng nghe:*
- Cổng TCP Socket Giám thị: `0.0.0.0:8090`
- Cổng Web Thí sinh làm bài thi: `http://0.0.0.0:8080/`

### Bước 2: Khởi động Console Giám thị (SM) & Giảng viên (PO)
Mở PowerShell 2:
```powershell
$env:RPMC_ADMIN_TOKEN = "admin_secret_token_12345678"
$env:RPMC_ALLOW_PRIVATE_NETWORK = "1"
python -m console.app
```
- Chuyển sang tab **"PO: Quy Chế & Điểm"** để thiết lập quy chế phòng thi.
- Chuyển sang tab **"SM: Giám Sát Thi"** để theo dõi danh sách thí sinh thời gian thực.

### Bước 3: Thí sinh tham gia làm bài thi
**Cách 1 (Web Browser):** Mở trình duyệt Chrome/Edge truy cập `http://localhost:8080` (hoặc `http://<IP_LAN_MAY_CHU>:8080` từ máy khác cùng mạng Wi-Fi/LAN).
- Nhập MSSV và Họ tên -> Bấm **Vào Phòng Thi**.
- Bấm **Bắt Đầu Làm Bài** để tự động kích hoạt **Toàn Màn Hình**.
- Thử bấm Alt+Tab hoặc chuyển tab: Màn hình thí sinh nhấp nháy cảnh báo đỏ và bị trừ điểm, đồng thời trên Console Giám thị lập tức nhảy thông báo đỏ.

**Cách 2 (Python TCP Socket thuần):** Mở PowerShell 3 chạy client mô phỏng:
```powershell
python -m scripts.student_tcp_client 127.0.0.1 8090 SV02 "Trần Văn Bình"
```

## 5. Verification

Chạy toàn bộ test kiểm thử tự động (Framing, dính/xé gói tin, tính điểm, live integration):
```powershell
python -m unittest discover tests -v
```


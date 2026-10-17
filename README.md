# RPMC - HỆ THỐNG QUẢN TRỊ TỪ XA & GIÁM SÁT THI TRỰC TUYẾN QUA MẠNG LAN

**RPMC (Remote Process & Machine Controller)** là nền tảng quản trị máy tính từ xa kết hợp **Hệ thống giám sát thi thời gian thực qua mạng LAN** phục vụ đồ án môn **Lập trình mạng** (vận hành theo mô hình **Scrum**). 

Hệ thống hoạt động trên nền tảng **TCP Socket thuần** với cấu trúc **gói tin nhị phân 12-byte header tự thiết kế** (chống dính/xé gói tin) kết hợp Web HTTP/SSE cho thí sinh làm bài thi.

---

## 🌟 TỔNG HỢP CÁC TÍNH NĂNG & CÔNG DỤNG CỦA HỆ THỐNG

### Phân Hệ 1: Giám Sát & Điều Hành Phòng Thi (Exam Proctoring System)

Hệ thống được thiết kế theo chuẩn phân quyền Scrum, phục vụ kỳ thi trung thực và minh bạch qua mạng nội bộ:

#### 1. Dành cho Giảng viên / Product Owner (Tab "PO: Quy Chế & Điểm")
- **Thiết lập quy chế phòng thi**:
  - Cấu hình thang điểm ban đầu (mặc định 10.0 điểm).
  - Cấu hình mức trừ điểm tự động cho mỗi lần vi phạm (ví dụ: -1.0 đ/lần).
  - Thiết lập ngưỡng vi phạm tối đa (ví dụ: quá 3 lần sẽ tự động đình chỉ/khóa bài thi).
  - Cài đặt thời gian làm bài thi và nội dung đề bài.
- **Bảng điểm tổng hợp thời gian thực**:
  - Tự động thống kê danh sách thí sinh, điểm số hiện tại, số lần vi phạm và trạng thái (`IN_PROGRESS`, `WARNED`, `LOCKED`, `SUBMITTED`).
- **Nghiệm thu & Xuất báo cáo**:
  - Xuất bảng điểm tổng hợp và nhật ký vết vi phạm ra định dạng CSV/JSON phục vụ lưu trữ học vụ.

#### 2. Dành cho Giám thị / Scrum Master (Tab "SM: Giám Sát Thi")
- **Theo dõi phòng thi thời gian thực (Real-time LAN Monitoring)**:
  - Lắng nghe và hiển thị tất cả thí sinh đang kết nối từ các máy tính khác trong mạng Wi-Fi/LAN.
  - Hiển thị trực quan MSSV, Họ tên, Địa chỉ IP, Điểm thi và Trạng thái thi theo mã màu (Xanh: An toàn, Vàng: Cảnh báo, Đỏ: Đã bị khóa).
- **Hộp thông báo gian lận trực tiếp (Live Alert Feed)**:
  - Nhận cảnh báo đẩy (Push Alert) tức thì ngay khi thí sinh thực hiện hành vi vi phạm:
    - `TAB_SWITCH`: Thí sinh chuyển tab trình duyệt sang Google, tài liệu,...
    - `BLUR`: Thí sinh chuyển cửa sổ ứng dụng khác, mất focus chuột khỏi bài thi.
    - `EXIT_FULLSCREEN`: Thí sinh thoát chế độ toàn màn hình.
    - Nhấn phím cấm (`F12` mở DevTools, `Alt+Tab`, `Ctrl+C/V` sao chép).
- **Quyền can thiệp từ xa của Giám thị (Intervention Tools)**:
  - **Gửi tin nhắn cảnh báo**: Gửi thông điệp nhắc nhở trực tiếp hiện lên màn hình của một thí sinh cụ thể.
  - **Ghi nhận vi phạm thủ công**: Trừ điểm hoặc cảnh cáo đối với các hành vi phát hiện qua mắt thường.
  - **Khóa bài thi cưỡng chế**: Lập tức vô hiệu hóa bài thi của thí sinh vi phạm nghiêm trọng.

#### 3. Dành cho Thí sinh / Developers (Client thi làm bài)
- **Giao diện làm bài trắc nghiệm Web mượt mà** (`web/`):
  - Truy cập dễ dàng từ trình duyệt Chrome/Edge trên bất kỳ máy tính/thiết bị nào trong mạng LAN (`http://<IP_MAY_CHU>:8081/`).
  - Tự động khóa toàn màn hình (Fullscreen) khi bấm bắt đầu làm bài.
  - Hiển thị HUD thời gian làm bài, điểm số trực tiếp (bị trừ ngay trên màn hình khi vi phạm).
  - Nhận và hiển thị hộp thoại cảnh báo từ Giám thị.
- **Client mô phỏng bằng Python TCP Socket thuần** (`scripts/student_tcp_client.py`):
  - Kết nối trực tiếp bằng Socket TCP nhị phân, gửi gói tin đăng ký, báo cáo sự kiện vi phạm và nhận phản hồi tính điểm thời gian thực.

---

### Phân Hệ 2: Quản Trị & Điều Khiển Máy Tính Từ Xa (RPMC Admin Console)

Phục vụ quản lý, hỗ trợ kỹ thuật và giám sát máy trạm trong phòng máy/mạng LAN:

1. **Dashboard Giám sát phần cứng**:
   - Tự động cập nhật mỗi 2 giây: Thông tin CPU, dung lượng RAM khả dụng, ổ đĩa Disk, địa chỉ IP mạng và hệ điều hành của máy con (Agent).
2. **Quản lý danh sách kết nối (Clients)**:
   - Theo dõi trạng thái kết nối/ngắt kết nối của toàn bộ máy trạm trong mạng nội bộ.
3. **Quản lý tiến trình từ xa (Processes)**:
   - Xem toàn bộ tiến trình đang chạy trên máy con (PID, Process Name, CPU%, Memory%).
   - Tìm kiếm tiến trình nghi vấn.
   - Hỗ trợ dừng/kết thúc tiến trình (Process Termination) với cơ chế bảo vệ an toàn: chặn kill tiến trình hệ thống, kiểm tra quyền sở hữu user và yêu cầu xác nhận token `RPMC_ALLOW_PROCESS_TERMINATION`.
4. **Quản lý tệp tin từ xa (Files)**:
   - Duyệt cây thư mục từ xa trên máy con.
   - Tải tệp tin (File Download) về máy quản trị.
   - Cơ chế Sandbox bảo mật: Giới hạn nghiêm ngặt trong thư mục được cấp phép (`RPMC_AGENT_ROOT`), chặn Path Traversal và từ chối tải file vượt quá 8 MiB.
5. **Truyền phát màn hình thời gian thực (Screen Stream)**:
   - Chụp màn hình máy con và truyền về máy quản trị theo kỹ thuật **JPEG Delta Tiles 64x64**.
   - Chỉ truyền các ô ảnh có sự thay đổi nội dung giúp tối ưu băng thông mạng LAN, đạt tốc độ 8 - 15 FPS mượt mà.
   - Hỗ trợ nút Start/Stop luồng truyền phát an toàn.
6. **Nhật ký kiểm toán bảo mật (Audit Log SHA-256 Chained)**:
   - Ghi lại toàn bộ hành vi nhạy cảm (kết nối, tải file, kill tiến trình, gửi lệnh).
   - Mã hóa liên kết chuỗi băm SHA-256 (tương tự Blockchain) đảm bảo tính toàn vẹn, chống chối bỏ và chống chỉnh sửa nhật ký trái phép; hỗ trợ nút xác thực tính toàn vẹn (Verify Integrity).
7. **SOC Terminal chuyên dụng**:
   - Cung cấp giao diện dòng lệnh quản trị chạy trên danh sách lệnh cho phép (Allowlist Commands), an toàn hơn Shell hệ điều hành thông thường.

---

### Phân Hệ 3: Các Cơ Chế Mạng & Kỹ Thuật Nổi Bật

- **Cấu hình 1 lần duy nhất qua file `.env`**: Tự động lưu Token và cấu hình mạng; không cần phải tạo ngẫu nhiên hay copy-paste token mỗi lần chạy trên PyCharm/Terminal.
- **Tự động dò cổng thông minh (Smart Port Fallback)**: Tự động phát hiện xung đột cổng (ví dụ cổng 8080 bị phần mềm khác chiếm) để tự chuyển sang cổng 8081/8082, không bao giờ bị dừng chương trình đột ngột (`WinError 10013`).
- **Chuẩn hóa địa chỉ mạng (IP Sanitization)**: Tự động cắt khoảng trắng thừa, hỗ trợ lắng nghe `0.0.0.0` đa card mạng và kiểm tra an toàn dải IP nội bộ theo chuẩn RFC 1918.

---

## 📐 CẤU TRÚC GÓI TIN TCP (WIRE FORMAT - 12 BYTES)

Để khắc phục hiện tượng **dính gói / xé gói** (Concatenation & Fragmentation) của giao thức TCP Stream:

| Byte Offset | Độ dài | Tên trường | Kiểu dữ liệu | Ý nghĩa |
| :--- | :--- | :--- | :--- | :--- |
| `0 - 1` | 2 bytes | `MAGIC_HEADER` | `>H` | `0x5352` ('SR') nhận diện gói tin chuẩn của hệ thống |
| `2` | 1 byte | `PROTOCOL_VERSION` | `>B` | `0x01` Phiên bản giao thức |
| `3` | 1 byte | `RESERVED` | `>B` | `0x00` Dự phòng mở rộng |
| `4 - 7` | 4 bytes | `PAYLOAD_LENGTH` | `>I` | Độ dài chính xác của phần thân dữ liệu ($N$ bytes) |
| `8 - 9` | 2 bytes | `FRAME_TYPE` | `>H` | `CONTROL (0x0001)`, `DATA (0x0002)` |
| `10 - 11` | 2 bytes | `COMMAND_TYPE` | `>H` | Mã lệnh xử lý (ví dụ: `0x0604` báo vi phạm) |
| `12 -> 12+N` | $N$ bytes | `PAYLOAD` | UTF-8 JSON | Dữ liệu nội dung của gói tin |

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & CHẠY ỨNG DỤNG (CẤU HÌNH 1 LẦN)

### 1. Chuẩn bị môi trường
Cài đặt thư viện phụ thuộc:
```powershell
python -m pip install -r requirements.txt
```

### 2. File cấu hình `.env` (Đã có sẵn trong thư mục gốc)
Hệ thống sử dụng file `.env` cố định:
```env
RPMC_ADMIN_TOKEN=AdminTokenNgauNhien32KyTu
RPMC_AGENT_TOKEN=AgentTokenNgauNhien32KyTu
RPMC_SERVER_PORT=8090
EXAM_HTTP_PORT=8081
RPMC_BIND_HOST=0.0.0.0
RPMC_ALLOW_PRIVATE_NETWORK=1
```

### 3. Khởi chạy trên PyCharm hoặc Terminal

#### Bước 1: Bật Máy Chủ (Server)
Chạy file `server/server_main.py`:
```powershell
python -m server.server_main
```
*Server sẽ mở 2 cổng mạng:*
- Cổng TCP Socket điều khiển/Giám sát: `0.0.0.0:8090`
- Cổng Web Thí sinh làm bài thi: `http://0.0.0.0:8081/`

#### Bước 2: Bật Bảng Điều Khiển Giám Thị & Quản Trị (Console)
Chạy file `console/app.py`:
```powershell
python -m console.app
```
*(Token đã được tự động điền sẵn, không cần nhập lại).*

#### Bước 3: Thí sinh tham gia làm bài thi
- **Cách 1 (Trình duyệt Web - Tiện nhất)**: Mở Chrome/Edge truy cập `http://localhost:8081` (hoặc `http://<IP_LAN_MAY_CHU>:8081` từ máy khác cùng Wi-Fi).
  - Nhập MSSV, Họ tên ➔ Bấm **Vào Phòng Thi** ➔ Bấm **Bắt Đầu Làm Bài**.
  - Thử nhấn Alt+Tab hoặc chuyển tab: Màn hình thí sinh nhấp nháy cảnh báo đỏ và bị trừ điểm, đồng thời trên Console Giám thị lập tức nhảy thông báo đỏ.
- **Cách 2 (Mô phỏng bằng Python TCP Socket)**:
  ```powershell
  python -m scripts.student_tcp_client 127.0.0.1 8090 SV02 "Trần Văn Bình"
  ```
- **Cách 3 (Máy trạm Agent giám sát sâu)**:
  ```powershell
  python -m agent.agent_main
  ```

---

## 🌐 KỊCH BẢN KẾT NỐI MẠNG LAN / WI-FI GIỮA CÁC MÁY THỰC TẾ

1. **Trên máy chủ**: Mở PowerShell gõ `ipconfig` lấy địa chỉ IPv4 (ví dụ: `192.168.1.15`). Khởi chạy `server_main.py` và `console/app.py`.
2. **Trên máy thí sinh khác (cùng Wi-Fi/LAN)**:
   - Mở trình duyệt web truy cập: `http://192.168.1.15:8081/` để làm bài thi.
   - Hoặc kết nối Agent từ xa:
     ```powershell
     $env:RPMC_SERVER_HOST = "192.168.1.15"
     $env:RPMC_SERVER_PORT = "8090"
     $env:RPMC_AGENT_TOKEN = "AgentTokenNgauNhien32KyTu"
     $env:RPMC_ALLOW_PRIVATE_NETWORK = "1"
     python -m agent.agent_main
     ```

---

## 🐘 HƯỚNG DẪN CÀI ĐẶT & KẾT NỐI POSTGRESQL TRÊN WINDOWS

Khi sử dụng chức năng lưu ngân hàng đề thi hoặc tạo kỳ thi lưu trữ vĩnh viễn, hệ thống RPMC sử dụng PostgreSQL.

### Bước 1: Tải và cài đặt PostgreSQL
1. Tải bộ cài chính thức dành cho Windows từ trang chủ: [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/) (khuyên dùng phiên bản 15 hoặc 16).
2. Trong quá trình cài đặt, ghi nhớ **mật khẩu của tài khoản `postgres`** mà bạn nhập.

### Bước 2: Thêm công cụ dòng lệnh PostgreSQL vào biến môi trường PATH
Để sử dụng được lệnh `psql` trong PowerShell / CMD:
1. Nhấn phím `Windows`, gõ **Environment Variables** (hoặc `Chỉnh sửa biến môi trường hệ thống`).
2. Trong mục **System variables**, chọn biến **Path** ➔ Bấm **Edit** ➔ Bấm **New**.
3. Thêm đường dẫn tới thư mục `bin` của PostgreSQL (mặc định là: `C:\Program Files\PostgreSQL\16\bin`).
4. Bấm **OK** để lưu lại và mở lại cửa sổ PowerShell mới để lệnh `psql` có hiệu lực.

### Bước 3: Tạo cơ sở dữ liệu `rpmc` và `rpmc_test`
Mở PowerShell và chạy 2 lệnh sau:
```powershell
psql -U postgres -c "CREATE DATABASE rpmc;"
psql -U postgres -c "CREATE DATABASE rpmc_test;"
```

### Bước 4: Cấu hình chuỗi kết nối trong file `.env`
Mở file `.env` trong thư mục gốc dự án và thêm dòng sau:
```env
RPMC_DB_DSN=postgresql://postgres:matkhau_cua_ban@localhost:5432/rpmc
```
> [!IMPORTANT]
> **Lưu ý mã hóa URL cho mật khẩu**: Nếu mật khẩu tài khoản PostgreSQL của bạn chứa ký tự đặc biệt (ví dụ: `@`, `#`, `$`, `%`, `:`, `/`), bạn phải mã hóa ký tự đó theo định dạng URL encoding trong chuỗi DSN:
> - Ký tự `@` ➔ `%40`
> - Ký tự `#` ➔ `%23`
> - Ký tự `$` ➔ `%24`
> - Ký tự `%` ➔ `%25`
> *Ví dụ: Mật khẩu là `p@ss#123` thì viết: `postgresql://postgres:p%40ss%23123@localhost:5432/rpmc`.*

### Bước 5: Khởi tạo cấu trúc bảng (Schema)
Chạy lệnh sau để tự động nạp `schema.sql` và `schema_v2.sql` theo đúng thứ tự (an toàn khi chạy lại nhiều lần):
```powershell
.venv\Scripts\python.exe -m question_bank init
```

### Bước 6: Kiểm tra môi trường tự động
Chạy script kiểm tra để đảm bảo toàn bộ thư viện, DSN, kết nối và bảng dữ liệu đã sẵn sàng:
```powershell
.venv\Scripts\python.exe -m scripts.check_db
```
*Script sẽ kiểm tra tuần tự 4 bước và báo kết quả `✅` trực quan.*

---

## 📝 HỆ THỐNG THI TRỰC TUYẾN WEB BƯỚC 2 (KIẾN TRÚC & API THÍ SINH)

### 1. Luồng thi trắc nghiệm trực tuyến (Exam Workflow)
1. **Đăng ký vào phòng thi**:
   - Thí sinh mở trình duyệt truy cập `http://<IP_MAY_CHU>:8081/`.
   - Nhập MSSV và Họ tên ➔ Bấm **Vào Phòng Thi**.
   - Server kiểm tra và cấp ngẫu nhiên `token` phiên thi bảo mật 32-bytes (`secrets.token_urlsafe(32)`).
   - Nếu thí sinh đã có phiên thi đang hoạt động hợp lệ mà đăng ký lại cùng MSSV, hệ thống sẽ từ chối với mã **HTTP 409 Conflict** kèm thông báo tiếng Việt nhằm chống chiếm dụng/ghi đè phiên thi trái phép.
2. **Kích hoạt chế độ thi Toàn Màn Hình**:
   - Thí sinh bấm **🚀 Bắt Đầu Làm Bài (Kích Hoạt Fullscreen)**.
   - Trình duyệt bật Fullscreen và bắt đầu đồng hồ đếm ngược được tính từ thời điểm kích hoạt của Server.
3. **Nạp đề thi cá nhân hóa & Làm bài**:
   - Web Client gọi API `/api/exam/questions` kèm header `X-Student-Token`.
   - Đề thi được xáo trộn thứ tự câu hỏi và thứ tự đáp án (A-D) ngẫu nhiên theo thuật toán băm MSSV (`seed = SHA256(MSSV)`). **TUYỆT ĐỐI không chứa `answer_key`** nhằm chống soi đáp án qua DevTools / F12.
4. **Lưu nháp câu trả lời & Cơ chế Hàng Đợi (Queue & Retry)**:
   - Mỗi lần chọn đáp án, client tự động gửi lưu nháp tới `/api/exam/save_draft` (idempotent, chỉ nhận A, B, C, D).
   - Phía Server áp dụng Rate Limit (0.2s/lần lưu) để chống spam.
   - Phía Client (`web/app.js`) tích hợp sẵn **Hàng đợi lưu nháp tự động (Save Queue)**:
     - Khi thí sinh bấm nhanh liên tiếp hoặc gặp mã lỗi `429 Too Many Requests` / mất kết nối mạng tạm thời, client tự động giữ lại đáp án, xếp hàng và thử lại (exponential backoff) tối đa 5 lần.
     - Hiển thị trực quan trạng thái trên thanh HUD: `⏳ Đang lưu...` ➔ `✓ Đã lưu` ➔ `⚠️ Lỗi lưu đáp án`.
     - Đảm bảo thí sinh bấm nhanh, chuyển câu liên tục không bao giờ bị mất đáp án.
5. **Khôi phục bài thi khi F5 tải lại trang**:
   - Nếu thí sinh vô tình nhấn F5 hoặc tải lại trang, client tự động đọc `token` từ `sessionStorage`, gọi `/api/exam/status` và `/api/exam/submissions` để khôi phục toàn bộ giao diện bài thi, đồng hồ và các đáp án đã chọn trước đó.
6. **Nộp bài & Thu bài tự động**:
   - Thí sinh có thể chủ động bấm **Nộp Bài Thi** bất kỳ lúc nào.
   - Khi hết giờ làm bài, bộ hẹn giờ nền trên Server (`ExamBackgroundTimer`) chạy độc lập tự động chốt trạng thái kỳ thi sang `FINISHED`, tự động thu bài và chấm điểm cho tất cả thí sinh đã đăng ký (thí sinh chưa làm câu nào vẫn được ghi dòng kết quả với `exam_score = 0.0`).

---

### 2. Quy trình "Cấp Lại Phiên Thi" cho Giám Thị (Session Re-issue)
Khi thí sinh gặp sự cố bất khả kháng (máy tính bị sập nguồn, hư hỏng phải đổi máy khác, hoặc lỡ đóng hẳn trình duyệt và mất token lưu tạm):
1. Thí sinh đăng ký lại từ máy mới sẽ nhận thông báo:
   > *"Thí sinh đã đăng ký và đang có phiên thi hợp lệ. Vui lòng liên hệ giám thị để cấp lại phiên nếu cần."* (HTTP 409).
2. **Thao tác của Giám thị trên Console** (Tab **SM: Giám Sát Thi**):
   - Chọn dòng của thí sinh đó trong bảng giám sát.
   - Bấm nút **"🔄 Cấp Lại Phiên Thi (Reset Session)"**.
   - Hộp thoại xác nhận hiện ra, giám thị nhập lý do (ví dụ: *"Thí sinh đổi sang máy PC-08"*).
3. **Cơ chế xử lý an toàn của Server**:
   - Token cũ của thí sinh lập tức bị **vô hiệu hóa** (mọi cuộc gọi API bằng token cũ sẽ bị từ chối với HTTP 401).
   - Ghi nhật ký kiểm toán: Action `SESSION_RESET` kèm MSSV, lý do và danh tính giám thị cấp lại. **Tuyệt đối không ghi token vào file nhật ký audit log**.
   - Bật cờ cho phép MSSV đó được đăng ký lại: Thí sinh đăng nhập lại từ máy mới sẽ thành công (HTTP 200) và nhận một Token hoàn toàn mới.
   - Toàn bộ các đáp án mà thí sinh đã lưu nháp trước đó vẫn được giữ nguyên vẹn.

---

### 3. Danh sách API Thí sinh & Chuẩn bảo mật Header

| Phương thức | Đường dẫn API | Mục đích | Token Header bắt buộc |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/exam/register` | Đăng ký vào phòng thi (Body: `{ student_id, name }`) | Không (API cấp token) |
| `GET` | `/api/exam/config` | Lấy cấu hình quy chế phòng thi và thời gian còn lại | Không |
| `GET` | `/api/exam/questions` | Lấy đề thi xáo trộn theo MSSV (không có answer_key) | `X-Student-Token` |
| `POST` | `/api/exam/save_draft` | Lưu nháp câu trả lời (Body: `{ question_id, chosen }`) | `X-Student-Token` |
| `GET` | `/api/exam/submissions`| Lấy danh sách đáp án đã lưu phục vụ khôi phục F5 | `X-Student-Token` |
| `GET` | `/api/exam/status` | Lấy trạng thái điểm, vi phạm, thời gian của thí sinh | `X-Student-Token` |
| `POST` | `/api/exam/submit` | Nộp bài thi chính thức và tính điểm tổng kết | `X-Student-Token` |
| `GET` | `/api/exam/events` | Luồng sự kiện Server-Sent Events (SSE) đẩy cảnh báo | Query `?token=...` hoặc Header |
| `POST` | `/api/exam/reset_session` | Giám thị cấp lại phiên thi (Body: `{ student_id, reason }`) | Quyền Giám thị (SM) |

> [!CAUTION]
> **Quy định bảo mật Token**:
> 1. Mọi API thông thường (`/api/exam/questions`, `/api/exam/save_draft`, `/api/exam/submissions`, `/api/exam/status`, `/api/exam/submit`) **chỉ chấp nhận token thông qua header** `X-Student-Token` hoặc `Authorization: Bearer <token>`. Nếu gửi token qua Query URL (ví dụ: `?token=...`), server sẽ **từ chối 401 Unauthorized** ngay lập tức nhằm chống rò rỉ token qua URL history, proxy và access log.
> 2. Chỉ có duy nhất endpoint `/api/exam/events` (do chuẩn trình duyệt `EventSource` của HTML5 không hỗ trợ gán custom headers) mới được phép truyền qua query parameter `?token=...`.
> 3. Tuyệt đối không ghi token thô vào file nhật ký audit log hay log hệ thống.

---

## 🧪 KIỂM THỬ TỰ ĐỘNG (VERIFICATION)

Chạy bộ kiểm thử tự động toàn diện:
```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
```

### Chạy kiểm thử tích hợp PostgreSQL thật (`rpmc_test`):
Thiết lập biến môi trường `RPMC_TEST_DSN` và chạy test:
```powershell
$env:RPMC_TEST_DSN = "postgresql://postgres:matkhau@localhost:5432/rpmc_test"
.venv\Scripts\python.exe -m unittest discover tests -v
```
Toàn bộ test suite sẽ chạy thành công và tự động dọn sạch dữ liệu test trong `rpmc_test`, tuyệt đối không tác động vào database chính `rpmc`.
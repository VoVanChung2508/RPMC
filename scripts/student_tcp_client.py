#!/usr/bin/env python3
"""
Mô phỏng Client Học sinh bằng Python TCP Socket thuần (Raw Binary Framing)
Minh họa trực quan cho đồ án Lập trình mạng:
- Mở kết nối TCP Socket tới Server qua mạng LAN.
- Đóng gói Frame nhị phân 12-byte header + JSON payload.
- Gửi sự kiện đăng ký và báo cáo vi phạm (TAB_SWITCH, BLUR, EXIT_FULLSCREEN).
- Nhận phản hồi tính điểm trực tiếp từ Server qua TCP stream.
"""

from __future__ import annotations

import json
import socket
import struct
import sys
import time

from common.protocol import CommandType, Frame, FrameCodec, FrameType


class StudentTCPClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8090, student_id: str = "SV01", name: str = "Nguyễn Văn An"):
        self.host = host
        self.port = port
        self.student_id = student_id
        self.name = name
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        print(f"[*] Đang kết nối TCP Socket tới Server {self.host}:{self.port}...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print("[+] Kết nối TCP thành công!")

    def send_frame(self, frame_type: FrameType, command_type: CommandType, payload_dict: dict) -> Frame:
        if self.sock is None:
            raise RuntimeError("Chưa kết nối Socket")
        payload_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
        frame = Frame(frame_type=frame_type, command_type=command_type, payload=payload_bytes)
        wire_data = FrameCodec.encode(frame)
        self.sock.sendall(wire_data)

        # Đọc gói tin phản hồi từ Server (xử lý chống dính/xé gói tin)
        response_frame = FrameCodec.read_frame(self.sock)
        return response_frame

    def register(self) -> dict:
        print(f"\n[1] Gửi gói tin TCP: Đăng ký thí sinh ({self.student_id} - {self.name})...")
        resp = self.send_frame(
            FrameType.CONTROL,
            CommandType.EXAM_STUDENT_REGISTER,
            {"student_id": self.student_id, "name": self.name},
        )
        data = json.loads(resp.payload.decode("utf-8"))
        print(f"[<-] Server phản hồi: Điểm khởi tạo = {data.get('score')} | Trạng thái = {data.get('status')}")
        return data

    def report_violation(self, event: str, detail: str) -> dict:
        print(f"\n[!] PHÁT HIỆN VI PHẠM: {event} ({detail})")
        print("[2] Gửi gói tin TCP vi phạm lên Server...")
        resp = self.send_frame(
            FrameType.CONTROL,
            CommandType.EXAM_VIOLATION_REPORT,
            {
                "student_id": self.student_id,
                "event": event,
                "detail": detail,
                "timestamp": time.time(),
            },
        )
        data = json.loads(resp.payload.decode("utf-8"))
        student = data.get("student", {})
        violation = data.get("violation", {})
        print(f"[<-] Server tính điểm: Bị trừ {violation.get('deduction')} đ -> Điểm còn lại: {student.get('score')} đ")
        print(f"[<-] Số lần vi phạm: {student.get('violation_count')} | Trạng thái: {student.get('status')}")
        if student.get("warning_message"):
            print(f"⚠️ THÔNG BÁO CỦA HỆ THỐNG: {student.get('warning_message')}")
        return data

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            print("[*] Đã đóng kết nối TCP Socket.")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
    student_id = sys.argv[3] if len(sys.argv) > 3 else "SV01"
    name = sys.argv[4] if len(sys.argv) > 4 else "Nguyễn Văn An"

    client = StudentTCPClient(host=host, port=port, student_id=student_id, name=name)
    try:
        client.connect()
        client.register()

        # Mô phỏng các sự kiện vi phạm
        time.sleep(1)
        client.report_violation("TAB_SWITCH", "Sinh viên chuyển sang tab trình duyệt khác")

        time.sleep(1)
        client.report_violation("BLUR", "Sinh viên bấm chuột ra ngoài cửa sổ bài thi (Alt+Tab)")

        time.sleep(1)
        client.report_violation("EXIT_FULLSCREEN", "Sinh viên bấm phím ESC thoát toàn màn hình")

    except Exception as ex:
        print(f"[-] Lỗi trong quá trình truyền nhận TCP: {ex}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

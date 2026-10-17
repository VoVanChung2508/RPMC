from __future__ import annotations

import json
import os
import struct
import unittest

from common.exam_models import ExamConfig, ExamStatus, StudentStatus
from common.protocol import CommandType, Frame, FrameCodec, FrameType
from server.exam_manager import ExamManager


class TestExamFramingProtocol(unittest.TestCase):
    def test_frame_encode_decode(self):
        payload = b'{"student_id":"SV01","event":"TAB_SWITCH"}'
        frame = Frame(
            frame_type=FrameType.CONTROL,
            command_type=CommandType.EXAM_VIOLATION_REPORT,
            payload=payload,
        )
        wire_bytes = FrameCodec.encode(frame)
        self.assertEqual(len(wire_bytes), 12 + len(payload))

        decoded = FrameCodec.decode(wire_bytes)
        self.assertEqual(decoded.frame_type, FrameType.CONTROL)
        self.assertEqual(decoded.command_type, CommandType.EXAM_VIOLATION_REPORT)
        self.assertEqual(decoded.payload, payload)

    def test_concatenated_frames_dinh_goi(self):
        """Kiểm tra xử lý hiện tượng dính gói: 2 gói tin TCP được nhận trong cùng 1 buffer"""
        payload1 = b'{"msg":"frame1"}'
        payload2 = b'{"msg":"frame2"}'

        f1 = Frame(FrameType.CONTROL, CommandType.EXAM_STUDENT_REGISTER, payload1)
        f2 = Frame(FrameType.CONTROL, CommandType.EXAM_VIOLATION_REPORT, payload2)

        buffer = FrameCodec.encode(f1) + FrameCodec.encode(f2)
        frames = FrameCodec.decode_buffer(buffer)

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].command_type, CommandType.EXAM_STUDENT_REGISTER)
        self.assertEqual(frames[0].payload, payload1)
        self.assertEqual(frames[1].command_type, CommandType.EXAM_VIOLATION_REPORT)
        self.assertEqual(frames[1].payload, payload2)

    def test_fragmented_frame_xe_goi(self):
        """Kiểm tra xử lý hiện tượng xé gói: buffer nhận chưa đủ kích thước header hoặc payload"""
        payload = b'{"long_message":"test_data_stream_fragmentation"}'
        frame = Frame(FrameType.CONTROL, CommandType.EXAM_VIOLATION_REPORT, payload)
        wire_bytes = FrameCodec.encode(frame)

        # Cắt đôi gói tin
        part1 = wire_bytes[:15]
        part2 = wire_bytes[15:]

        # Buffer chưa đủ toàn bộ frame -> decode_buffer trả về rỗng
        frames_partial = FrameCodec.decode_buffer(part1)
        self.assertEqual(len(frames_partial), 0)

        # Sau khi nhận tiếp mảnh 2
        frames_full = FrameCodec.decode_buffer(part1 + part2)
        self.assertEqual(len(frames_full), 1)
        self.assertEqual(frames_full[0].payload, payload)


class TestExamManagerLogic(unittest.TestCase):
    def setUp(self):
        self.audit_file = "data/test_exam_audit.jsonl"
        if os.path.exists(self.audit_file):
            os.remove(self.audit_file)
        self.manager = ExamManager(log_path=self.audit_file)
        self.manager.config = ExamConfig(
            initial_score=10.0,
            penalty_per_violation=1.5,
            max_violations=3,
            duration_minutes=30,
        )
        self.manager.students.clear()

    def tearDown(self):
        if os.path.exists(self.audit_file):
            os.remove(self.audit_file)

    def test_student_registration_and_scoring(self):
        student = self.manager.register_student("SV01", "Trần Văn B", "192.168.1.10")
        self.assertEqual(student.student_id, "SV01")
        self.assertEqual(student.score, 10.0)
        self.assertEqual(len(student.violations), 0)

        # Vi phạm lần 1: TAB_SWITCH (-1.5 đ)
        student, rec1 = self.manager.record_violation("SV01", "TAB_SWITCH", "Chuyển tab")
        self.assertEqual(student.score, 8.5)
        self.assertEqual(len(student.violations), 1)
        self.assertEqual(student.status, StudentStatus.WARNED)

        # Vi phạm lần 2: BLUR (-1.5 đ)
        student, rec2 = self.manager.record_violation("SV01", "BLUR", "Mất focus")
        self.assertEqual(student.score, 7.0)
        self.assertEqual(len(student.violations), 2)

        # Vi phạm lần 3: EXIT_FULLSCREEN -> Đạt ngưỡng max_violations (3 lần) -> Khóa bài!
        student, rec3 = self.manager.record_violation("SV01", "EXIT_FULLSCREEN", "Thoát F11")
        self.assertEqual(student.score, 5.5)
        self.assertEqual(len(student.violations), 3)
        self.assertEqual(student.status, StudentStatus.LOCKED)
        self.assertIn("KHÓA", student.warning_message)

    def test_realtime_broadcast_event(self):
        q = self.manager.subscribe()
        try:
            self.manager.register_student("SV02", "Lê Thị C", "192.168.1.20")
            event = q.get(timeout=1.0)
            self.assertEqual(event.get("type"), "STUDENT_JOIN")
            self.assertEqual(event.get("student", {}).get("student_id"), "SV02")
        finally:
            self.manager.unsubscribe(q)

    def test_csv_report_export(self):
        self.manager.register_student("SV03", "Hoàng Nam", "192.168.1.30")
        self.manager.record_violation("SV03", "TAB_SWITCH", "Chuyển tab")
        csv_text = self.manager.export_csv_report()
        self.assertIn("SV03", csv_text)
        self.assertIn("Hoàng Nam", csv_text)
        self.assertIn("8.5", csv_text)


if __name__ == "__main__":
    unittest.main()

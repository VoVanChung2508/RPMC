"""Shim tương thích ngược cho exam_editor_server ở thư mục gốc.

Tệp tin gốc đã được tổ chức lại tại: tools/exam_editor/exam_editor_server.py
Mô-đun này chuyển tiếp toàn bộ chức năng để đảm bảo các lệnh cũ và test suite hoạt động bình thường.
"""
from __future__ import annotations

import sys
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent / "tools" / "exam_editor"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from tools.exam_editor.exam_editor_server import *  # noqa: F401, F403
import tools.exam_editor.exam_editor_server as _server_module

# Giữ nguyên các tham chiếu module-level cho test patch và mock
Handler = _server_module.Handler
ExamEditorServer = _server_module.ExamEditorServer
main = _server_module.main

if __name__ == "__main__":
    _server_module.main()

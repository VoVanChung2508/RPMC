from __future__ import annotations  # Hỗ trợ type hint nâng cao

import os  # Làm việc với hệ điều hành
from pathlib import Path  # Xử lý đường dẫn tệp
from common.security import PathValidator  # Kiểm tra đường dẫn an toàn


class FileService:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir  # Thư mục gốc được phép truy cập

    def list_files(self, relative_path: str = "."):
        root = Path(self.root_dir).expanduser().resolve()  # Chuẩn hóa đường dẫn gốc
        target = PathValidator.validate(str(root), relative_path)  # Kiểm tra đường dẫn
        if not target.is_dir():
            raise NotADirectoryError(relative_path)  # Báo lỗi nếu không phải thư mục

        entries = []
        # Sắp xếp thư mục lên trước, sau đó đến tệp theo tên
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            entries.append(
                {
                    "path": str(item.relative_to(root)),  # Đường dẫn tương đối
                    "name": item.name,  # Tên tệp hoặc thư mục
                    "is_dir": item.is_dir(),  # Có phải thư mục không
                    "size": item.stat().st_size if item.is_file() else 0,  # Kích thước tệp
                    "modified": item.stat().st_mtime,  # Thời điểm chỉnh sửa cuối
                }
            )
        return entries  # Trả về danh sách tệp và thư mục

    def read_bytes(self, relative_path: str, max_bytes: int = 8 * 1024 * 1024) -> bytes:
        target = PathValidator.validate(self.root_dir, relative_path)  # Kiểm tra đường dẫn an toàn
        if not target.is_file():
            raise FileNotFoundError(relative_path)  # Báo lỗi nếu tệp không tồn tại
        size = target.stat().st_size  # Lấy kích thước tệp
        if size > max_bytes:
            raise ValueError(f"File exceeds the {max_bytes}-byte transfer limit")  # Giới hạn 8 MB
        return target.read_bytes()  # Đọc và trả về dữ liệu dạng bytes
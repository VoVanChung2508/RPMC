from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """
    Nạp các biến môi trường từ file .env vào os.environ nếu chưa tồn tại.
    Giúp cấu hình token và thông số cố định một lần duy nhất,
    không cần copy-paste hay sinh token mới mỗi khi chạy trên PyCharm/Terminal.
    """
    env_path = Path(path)
    if not env_path.is_file():
        # Tìm tại thư mục gốc dự án
        project_root = Path(__file__).resolve().parent.parent / ".env"
        if project_root.is_file():
            env_path = project_root
        else:
            return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass

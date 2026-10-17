import os
from pathlib import Path

# Đảm bảo toàn bộ test suite chạy mặc định ở chế độ In-Memory,
# tuyệt đối không nạp RPMC_DB_DSN từ .env để tránh tác động vào database thật (rpmc).
os.environ.setdefault("RPMC_REPO", "memory")

# Tự động nạp RPMC_TEST_DSN từ file .env nếu chưa có trong biến môi trường
if not os.environ.get("RPMC_TEST_DSN"):
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("RPMC_TEST_DSN="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ["RPMC_TEST_DSN"] = val
                    break
        except Exception:
            pass

-- ====================================================================
-- schema_v3.sql: Migration mở rộng quy chế thi, nhật ký vi phạm,
--                quản lý máy trạm (agents) và kiểm toán bảo mật SHA-256
-- Áp dụng: psql -U postgres -d rpmc -f schema_v3.sql
-- ====================================================================

-- 1. Cấu hình quy chế phòng thi cho từng kỳ thi (PO: Quy chế & Điểm)
CREATE TABLE IF NOT EXISTS exam_configs (
    exam_id                 INTEGER PRIMARY KEY REFERENCES exams(id) ON DELETE CASCADE,
    base_score              NUMERIC(5,2) NOT NULL DEFAULT 10.0,
    penalty_per_violation   NUMERIC(5,2) NOT NULL DEFAULT 1.0,
    max_violations          INTEGER NOT NULL DEFAULT 3,
    auto_lock_on_max        BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2. Nhật ký sự kiện vi phạm thời gian thực của thí sinh (Live Alert Feed)
CREATE TABLE IF NOT EXISTS exam_violations (
    id                  BIGSERIAL PRIMARY KEY,
    exam_id             INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id          TEXT NOT NULL,
    violation_type      VARCHAR(50) NOT NULL,
    penalty_applied     NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    detail              TEXT,
    created_by          TEXT NOT NULL DEFAULT 'SYSTEM',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_violations_student ON exam_violations(exam_id, student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_violations_exam ON exam_violations(exam_id, created_at DESC);

-- 3. Danh sách máy trạm (Agents) kết nối vào mạng LAN
CREATE TABLE IF NOT EXISTS agents (
    client_id           VARCHAR(50) PRIMARY KEY,
    hostname            VARCHAR(100),
    ip_address          VARCHAR(45),
    mac_address         VARCHAR(50),
    os_info             TEXT,
    cpu_count           INTEGER,
    total_ram_bytes     BIGINT,
    is_online           BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT now(),
    registered_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Lịch sử hiệu năng phần cứng định kỳ của máy trạm (CPU, RAM, Disk)
CREATE TABLE IF NOT EXISTS agent_hardware_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    client_id           VARCHAR(50) NOT NULL REFERENCES agents(client_id) ON DELETE CASCADE,
    cpu_percent         NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    ram_percent         NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    disk_percent        NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_metrics_time ON agent_hardware_metrics(client_id, recorded_at DESC);

-- 5. Nhật ký kiểm toán bảo mật liên kết chuỗi băm SHA-256 (Audit Log Chained Hash)
CREATE TABLE IF NOT EXISTS system_audit_logs (
    id                  BIGSERIAL PRIMARY KEY,
    sequence_id         BIGINT UNIQUE NOT NULL,
    action              VARCHAR(50) NOT NULL,
    role                VARCHAR(20) NOT NULL,
    client_id           VARCHAR(50) REFERENCES agents(client_id) ON DELETE SET NULL,
    ip_address          VARCHAR(45),
    details             JSONB,
    prev_hash           CHAR(64) NOT NULL,
    entry_hash          CHAR(64) UNIQUE NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_seq ON system_audit_logs(sequence_id ASC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON system_audit_logs(action, timestamp DESC);

-- ====================================================================
-- schema_v2.sql: Migration mở rộng trạng thái kỳ thi và kết quả bài làm
-- Áp dụng: psql -U postgres -d rpmc -f schema_v2.sql
-- Không sửa đè schema.sql ban đầu
-- ====================================================================

-- 1. Bổ sung các cột trạng thái vào bảng exams:
-- - status: 'CREATED' (mới tạo), 'IN_PROGRESS' (đang thi), 'FINISHED' (kết thúc)
-- - is_active: Đánh dấu kỳ thi nào đang được kích hoạt cho phòng thi
-- - started_at: Thời điểm server kích hoạt thi (server dùng mốc này để tính đếm ngược)
-- - ended_at: Thời điểm kết thúc kỳ thi
ALTER TABLE exams ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'CREATED';
ALTER TABLE exams ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE exams ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE exams ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;

-- 2. Chỉ mục cho truy vấn kỳ thi đang kích hoạt
CREATE INDEX IF NOT EXISTS idx_exams_is_active ON exams(is_active);

-- 3. Bảng lưu trữ kết quả tổng hợp của thí sinh (chịu được khởi động lại server)
CREATE TABLE IF NOT EXISTS student_exam_results (
    exam_id             INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id          TEXT    NOT NULL,
    exam_score          NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    violation_penalty   NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    final_score         NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    violation_count     INTEGER NOT NULL DEFAULT 0,
    status              VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    submitted_at        TIMESTAMPTZ,
    PRIMARY KEY (exam_id, student_id)
);

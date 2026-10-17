-- Ngân hàng đề thi RPMC (PostgreSQL 13+)
-- Chạy: psql -U postgres -d rpmc -f schema.sql

CREATE TABLE IF NOT EXISTS question_banks (
    id          SERIAL PRIMARY KEY,
    title       TEXT        NOT NULL,
    subject     TEXT,
    source_file TEXT,
    file_sha256 CHAR(64),                       -- chống nhập trùng cùng một file
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (file_sha256)
);

CREATE TABLE IF NOT EXISTS questions (
    id          SERIAL PRIMARY KEY,
    bank_id     INTEGER NOT NULL REFERENCES question_banks(id) ON DELETE CASCADE,
    q_no        INTEGER NOT NULL,               -- số câu trong file gốc
    content     TEXT    NOT NULL,
    answer_key  CHAR(1) NOT NULL CHECK (answer_key IN ('A','B','C','D')),
    points      NUMERIC(5,2) NOT NULL DEFAULT 1.0,
    UNIQUE (bank_id, q_no)
);

CREATE TABLE IF NOT EXISTS question_options (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    label       CHAR(1) NOT NULL CHECK (label IN ('A','B','C','D')),
    content     TEXT    NOT NULL,
    PRIMARY KEY (question_id, label)
);

-- Đề thi được dựng từ ngân hàng (chọn N câu, có thể xáo trộn)
CREATE TABLE IF NOT EXISTS exams (
    id               SERIAL PRIMARY KEY,
    bank_id          INTEGER NOT NULL REFERENCES question_banks(id),
    title            TEXT    NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 45,
    question_count   INTEGER,                   -- NULL = lấy toàn bộ
    shuffle          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bài làm của thí sinh
CREATE TABLE IF NOT EXISTS submissions (
    exam_id     INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id  TEXT    NOT NULL,               -- MSSV
    question_id INTEGER NOT NULL REFERENCES questions(id),
    chosen      CHAR(1) CHECK (chosen IN ('A','B','C','D')),
    saved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (exam_id, student_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_questions_bank ON questions(bank_id);

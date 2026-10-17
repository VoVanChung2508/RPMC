"""Đọc file Word (.docx) theo định dạng:

    Câu 1. Nội dung câu hỏi?
    A. ...
    B. ...
    C. ...
    D. ...
    Đáp án: B

Trả về danh sách câu hỏi + danh sách lỗi (để giảng viên sửa file).
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field

from docx import Document

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MiB

RE_QUESTION = re.compile(r"^C[âa]u\s*(\d+)\s*[.:)]\s*(.*)$", re.IGNORECASE)
RE_OPTION = re.compile(r"^([A-D])\s*[.)]\s*(.*)$")
RE_ANSWER = re.compile(r"^[ĐD][áa]p\s*[áa]n\s*[:：]\s*([A-D])\b", re.IGNORECASE)


@dataclass
class ParsedQuestion:
    no: int
    content: str
    options: dict[str, str] = field(default_factory=dict)
    answer: str | None = None


@dataclass
class ParseResult:
    questions: list[ParsedQuestion]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.questions) and not self.errors


def _paragraph_texts(doc):
    """Duyệt đoạn văn; mỗi đoạn có thể chứa xuống dòng mềm (Shift+Enter)."""
    for p in doc.paragraphs:
        for line in p.text.splitlines():
            line = line.strip()
            if line:
                yield line


def validate_docx_file(path: str) -> None:
    import os

    if not path.lower().endswith(".docx"):
        raise ValueError("Chỉ chấp nhận file .docx")
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise ValueError("File vượt quá 10 MiB")
    if not zipfile.is_zipfile(path):
        raise ValueError("File không phải .docx hợp lệ")


def parse_docx(path: str) -> ParseResult:
    validate_docx_file(path)
    doc = Document(path)

    questions: list[ParsedQuestion] = []
    errors: list[str] = []
    cur: ParsedQuestion | None = None

    for line in _paragraph_texts(doc):
        if m := RE_QUESTION.match(line):
            cur = ParsedQuestion(no=int(m.group(1)), content=m.group(2).strip())
            questions.append(cur)
        elif cur is None:
            continue  # bỏ qua tiêu đề/lời dẫn trước câu 1
        elif m := RE_ANSWER.match(line):
            cur.answer = m.group(1).upper()
        elif m := RE_OPTION.match(line):
            label = m.group(1)
            if label in cur.options:
                errors.append(f"Câu {cur.no}: đáp án {label} bị lặp")
            cur.options[label] = m.group(2).strip()
        else:
            # dòng nối tiếp của câu hỏi hoặc của đáp án cuối cùng
            if cur.options:
                last = list(cur.options)[-1]
                cur.options[last] += " " + line
            else:
                cur.content += " " + line

    errors.extend(validate_questions(questions))
    return ParseResult(questions, errors)


def validate_questions(questions: list[ParsedQuestion]) -> list[str]:
    """Kiểm tra danh sách câu hỏi (dùng chung cho parser và form chỉnh sửa)."""
    errors: list[str] = []
    seen: set[int] = set()
    for q in questions:
        if q.no in seen:
            errors.append(f"Câu {q.no}: số câu bị trùng")
        seen.add(q.no)
        if not q.content.strip():
            errors.append(f"Câu {q.no}: thiếu nội dung câu hỏi")
        if sorted(q.options) != ["A", "B", "C", "D"]:
            errors.append(
                f"Câu {q.no}: cần đủ 4 đáp án A-D (đang có: {''.join(sorted(q.options)) or 'không có'})"
            )
        elif any(not v.strip() for v in q.options.values()):
            errors.append(f"Câu {q.no}: có đáp án rỗng")
        if q.answer is None:
            errors.append(f"Câu {q.no}: chưa chọn đáp án đúng")
        elif q.answer not in q.options:
            errors.append(f"Câu {q.no}: đáp án {q.answer} không tồn tại trong A-D")

    if not questions:
        errors.append("Không tìm thấy câu hỏi nào (mỗi câu phải bắt đầu bằng 'Câu 1.')")
    return errors

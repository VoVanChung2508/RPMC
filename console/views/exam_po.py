from __future__ import annotations

import os
from tkinter import filedialog, messagebox
import customtkinter as ctk

from console.theme import CyberpunkTheme


def build_exam_po(root, request):
    frame = ctk.CTkFrame(root, fg_color="transparent")

    # Header
    header_box = ctk.CTkFrame(frame, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    header_box.pack(fill="x", padx=12, pady=(12, 8))

    ctk.CTkLabel(
        header_box,
        text="🎓 PRODUCT OWNER / GIẢNG VIÊN (CẤU HÌNH QUY CHẾ & BÁO CÁO TỔNG KẾT)",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=18, weight="bold"),
        text_color=CyberpunkTheme.PURPLE,
    ).pack(side="left", padx=16, pady=12)

    btn_refresh = ctk.CTkButton(
        header_box,
        text="Tải Lại Dữ Liệu",
        width=120,
        height=32,
        fg_color=CyberpunkTheme.CYAN,
        text_color="#000000",
        command=lambda: load_all_data(),
    )
    btn_refresh.pack(side="right", padx=16, pady=12)

    # Split: Left (Config Panel), Right (Report & Audit Panel)
    split_box = ctk.CTkFrame(frame, fg_color="transparent")
    split_box.pack(fill="both", expand=True, padx=12, pady=4)

    # Left: Exam Rules Configuration
    left_cfg = ctk.CTkFrame(split_box, width=380, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    left_cfg.pack(side="left", fill="y", padx=(0, 6))
    left_cfg.pack_propagate(False)

    ctk.CTkLabel(
        left_cfg,
        text="Thiết Lập Quy Chế Phòng Thi",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=15, weight="bold"),
        text_color=CyberpunkTheme.TEXT_WHITE,
    ).pack(anchor="w", padx=16, pady=(14, 12))

    # Initial Score
    ctk.CTkLabel(left_cfg, text="Điểm ban đầu (thang điểm):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_init_score = ctk.CTkEntry(left_cfg)
    entry_init_score.pack(fill="x", padx=16, pady=(0, 8))
    entry_init_score.insert(0, "10.0")

    # Penalty per violation
    ctk.CTkLabel(left_cfg, text="Mức trừ điểm / mỗi lần vi phạm:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_penalty = ctk.CTkEntry(left_cfg)
    entry_penalty.pack(fill="x", padx=16, pady=(0, 8))
    entry_penalty.insert(0, "1.0")

    # Max violations
    ctk.CTkLabel(left_cfg, text="Số lần vi phạm tối đa (bị khóa bài):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_max_viol = ctk.CTkEntry(left_cfg)
    entry_max_viol.pack(fill="x", padx=16, pady=(0, 8))
    entry_max_viol.insert(0, "3")

    # Duration
    ctk.CTkLabel(left_cfg, text="Thời gian làm bài thi (phút):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_duration = ctk.CTkEntry(left_cfg)
    entry_duration.pack(fill="x", padx=16, pady=(0, 8))
    entry_duration.insert(0, "45")

    # Exam Title
    ctk.CTkLabel(left_cfg, text="Tiêu đề kỳ thi:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_title = ctk.CTkEntry(left_cfg)
    entry_title.pack(fill="x", padx=16, pady=(0, 16))
    entry_title.insert(0, "ĐỀ THI MÔN LẬP TRÌNH MẠNG")

    def save_configuration():
        try:
            cfg = {
                "initial_score": float(entry_init_score.get().strip()),
                "penalty_per_violation": float(entry_penalty.get().strip()),
                "max_violations": int(entry_max_viol.get().strip()),
                "duration_minutes": int(entry_duration.get().strip()),
                "exam_title": entry_title.get().strip(),
            }
        except ValueError:
            messagebox.showerror("Lỗi", "Vui lòng nhập số hợp lệ vào các trường cấu hình!")
            return

        def on_saved(res):
            messagebox.showinfo("Thành công", "Đã lưu và áp dụng quy chế thi mới thành công!")
            load_all_data()

        request("exam.config.set", on_saved, config=cfg)

    btn_save_cfg = ctk.CTkButton(
        left_cfg,
        text="💾 Áp Dụng Cấu Hình Mới",
        height=38,
        fg_color=CyberpunkTheme.PURPLE,
        font=ctk.CTkFont(weight="bold"),
        command=save_configuration,
    )
    btn_save_cfg.pack(fill="x", padx=16, pady=(4, 12))

    # Right: Results Summary & Export
    right_report = ctk.CTkFrame(split_box, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    right_report.pack(side="right", fill="both", expand=True, padx=(6, 0))

    r_top = ctk.CTkFrame(right_report, fg_color="transparent")
    r_top.pack(fill="x", padx=16, pady=(14, 8))

    ctk.CTkLabel(
        r_top,
        text="Báo Cáo Điểm Số & Vết Vi Phạm Cuối Kỳ",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=15, weight="bold"),
        text_color=CyberpunkTheme.GREEN,
    ).pack(side="left")

    def export_csv():
        def on_export(res):
            csv_content = res.get("csv", "")
            save_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Lưu báo cáo điểm thi",
            )
            if save_path:
                try:
                    with open(save_path, "w", encoding="utf-8-sig") as f:
                        f.write(csv_content)
                    messagebox.showinfo("Thành công", f"Đã xuất báo cáo điểm ra:\n{save_path}")
                except Exception as ex:
                    messagebox.showerror("Lỗi", f"Không thể lưu file: {ex}")

        request("exam.report.export", on_export)

    btn_export = ctk.CTkButton(
        r_top,
        text="📥 Xuất Báo Cáo CSV",
        fg_color=CyberpunkTheme.GREEN,
        command=export_csv,
    )
    btn_export.pack(side="right")

    # Table of final scores
    tbl_hdr = ctk.CTkFrame(right_report, fg_color=CyberpunkTheme.PANEL_BORDER, height=30)
    tbl_hdr.pack(fill="x", padx=16, pady=(0, 4))
    ctk.CTkLabel(tbl_hdr, text="MSSV", width=100, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Họ và Tên", width=180, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Điểm Cuối", width=80, anchor="center", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Số Vi Phạm", width=80, anchor="center", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Trạng Thái", width=100, anchor="center", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)

    scores_scroll = ctk.CTkScrollableFrame(right_report, fg_color="transparent")
    scores_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def load_all_data():
        def on_cfg(res):
            cfg = res.get("config", {})
            entry_init_score.delete(0, "end")
            entry_init_score.insert(0, str(cfg.get("initial_score", 10.0)))
            entry_penalty.delete(0, "end")
            entry_penalty.insert(0, str(cfg.get("penalty_per_violation", 1.0)))
            entry_max_viol.delete(0, "end")
            entry_max_viol.insert(0, str(cfg.get("max_violations", 3)))
            entry_duration.delete(0, "end")
            entry_duration.insert(0, str(cfg.get("duration_minutes", 45)))
            entry_title.delete(0, "end")
            entry_title.insert(0, str(cfg.get("exam_title", "")))

        def on_students(res):
            for w in scores_scroll.winfo_children():
                w.destroy()
            students = res.get("students", [])
            for s in students:
                sid = s.get("student_id", "")
                name = s.get("name", "")
                score = s.get("score", 10.0)
                v_cnt = s.get("violation_count", 0)
                status = s.get("status", "")

                row = ctk.CTkFrame(scores_scroll, fg_color="transparent", height=28)
                row.pack(fill="x", pady=2)

                ctk.CTkLabel(row, text=sid, width=100, anchor="w", text_color=CyberpunkTheme.CYAN).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=name, width=180, anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(row, text=f"{score:.1f}", width=80, anchor="center", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=str(v_cnt), width=80, anchor="center", text_color=CyberpunkTheme.RED if v_cnt > 0 else CyberpunkTheme.TEXT_MUTED).pack(side="left", padx=4)

                st_color = CyberpunkTheme.GREEN
                if status == "LOCKED":
                    st_color = CyberpunkTheme.RED
                elif status == "WARNED":
                    st_color = CyberpunkTheme.YELLOW
                elif status == "SUBMITTED":
                    st_color = CyberpunkTheme.CYAN

                ctk.CTkLabel(row, text=status, width=100, anchor="center", text_color=st_color).pack(side="left", padx=4)

        request("exam.config.get", on_cfg)
        request("exam.students.list", on_students)

    frame.after(600, load_all_data)
    return frame

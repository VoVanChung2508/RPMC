from __future__ import annotations

import os
import webbrowser
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
        text="🎓 PRODUCT OWNER / GIẢNG VIÊN (CẤU HÌNH KỲ THI & BÁO CÁO TỔNG KẾT)",
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

    # Split: Left (Exam Creation & Rules Config), Right (Report & Audit Panel)
    split_box = ctk.CTkFrame(frame, fg_color="transparent")
    split_box.pack(fill="both", expand=True, padx=12, pady=4)

    # Left: Scrollable configuration panel
    left_cfg = ctk.CTkScrollableFrame(split_box, width=420, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    left_cfg.pack(side="left", fill="both", padx=(0, 6))

    # --- KHUNG 1: NHẬP ĐỀ TỪ WORD (MỞ TRANG EXAM EDITOR) ---
    def open_word_importer():
        editor_port = os.environ.get("EXAM_EDITOR_PORT", "8082")
        url = f"http://127.0.0.1:{editor_port}/"
        webbrowser.open(url)

    btn_open_editor = ctk.CTkButton(
        left_cfg,
        text="📂 Nhập Đề Từ File Word (.docx)",
        height=38,
        fg_color=CyberpunkTheme.CYAN,
        text_color="#000000",
        font=ctk.CTkFont(weight="bold"),
        command=open_word_importer,
    )
    btn_open_editor.pack(fill="x", padx=16, pady=(14, 2))
    ctk.CTkLabel(
        left_cfg,
        text="*Mở trang web http://127.0.0.1:8082 để tải lên, chỉnh sửa và lưu đề",
        font=ctk.CTkFont(size=11),
        text_color=CyberpunkTheme.TEXT_MUTED,
    ).pack(anchor="w", padx=16, pady=(0, 12))

    # --- KHUNG 2: TẠO KỲ THI TỪ NGÂN HÀNG ĐỀ ---
    ctk.CTkLabel(
        left_cfg,
        text="1. Tạo Kỳ Thi Từ Ngân Hàng Đề",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=15, weight="bold"),
        text_color=CyberpunkTheme.TEXT_WHITE,
    ).pack(anchor="w", padx=16, pady=(4, 8))

    ctk.CTkLabel(left_cfg, text="Chọn ngân hàng đề thi:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))

    bank_items: list[dict] = []
    row_bank_select = ctk.CTkFrame(left_cfg, fg_color="transparent")
    row_bank_select.pack(fill="x", padx=16, pady=(0, 8))

    combo_banks = ctk.CTkComboBox(row_bank_select, values=["-- Đang tải ngân hàng đề... --"], state="readonly")
    combo_banks.pack(side="left", fill="x", expand=True, padx=(0, 6))

    btn_reload_banks = ctk.CTkButton(
        row_bank_select,
        text="🔄 Làm mới",
        width=85,
        fg_color=CyberpunkTheme.CYAN,
        text_color="#000000",
        font=ctk.CTkFont(size=12, weight="bold"),
        command=lambda: load_banks_only(),
    )
    btn_reload_banks.pack(side="right")

    ctk.CTkLabel(left_cfg, text="Tên kỳ thi:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_exam_name = ctk.CTkEntry(left_cfg)
    entry_exam_name.pack(fill="x", padx=16, pady=(0, 8))
    entry_exam_name.insert(0, "Kỳ Thi Môn Lập Trình Mạng")

    ctk.CTkLabel(left_cfg, text="Số câu hỏi (để trống = lấy toàn bộ):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_q_count = ctk.CTkEntry(left_cfg, placeholder_text="Ví dụ: 20 hoặc để trống")
    entry_q_count.pack(fill="x", padx=16, pady=(0, 8))

    ctk.CTkLabel(left_cfg, text="Thời gian làm bài thi (phút):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_duration = ctk.CTkEntry(left_cfg)
    entry_duration.pack(fill="x", padx=16, pady=(0, 8))
    entry_duration.insert(0, "45")

    var_shuffle = ctk.BooleanVar(value=True)
    chk_shuffle = ctk.CTkCheckBox(left_cfg, text="Xáo trộn câu hỏi & thứ tự đáp án (Shuffle)", variable=var_shuffle)
    chk_shuffle.pack(anchor="w", padx=16, pady=(4, 4))

    ctk.CTkLabel(
        left_cfg,
        text="💡 Random theo MSSV: Mỗi học sinh sẽ được Server tự động xáo trộn câu hỏi & đáp án A-B-C-D. Nếu điền 'Số câu hỏi' (vd 20/30), mỗi em sẽ nhận ngẫu nhiên một bộ câu hỏi khác nhau.",
        font=ctk.CTkFont(size=11),
        text_color=CyberpunkTheme.CYAN,
        wraplength=380,
        justify="left",
    ).pack(anchor="w", padx=16, pady=(0, 12))

    def on_create_exam():
        sel = combo_banks.get()
        if not sel or not bank_items or sel.startswith("--"):
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một ngân hàng đề hợp lệ hoặc bấm Làm mới!")
            return

        is_random_mode = sel.startswith("🎲")
        if is_random_mode:
            selected_bank = bank_items[0]
            exam_title = entry_exam_name.get().strip()
            if not exam_title.startswith("[RANDOM]"):
                exam_title = f"[RANDOM] {exam_title}"
        else:
            selected_bank = None
            for b in bank_items:
                disp = f"#{b['id']} - {b['title']} ({b.get('question_count', 0)} câu)"
                if disp == sel:
                    selected_bank = b
                    break

            if not selected_bank:
                messagebox.showwarning("Cảnh báo", "Không tìm thấy ngân hàng đề được chọn!")
                return
            exam_title = entry_exam_name.get().strip()

        if not exam_title:
            messagebox.showerror("Lỗi", "Vui lòng nhập tên kỳ thi!")
            return

        try:
            dur = int(entry_duration.get().strip())
            q_cnt_raw = entry_q_count.get().strip()
            q_cnt = int(q_cnt_raw) if q_cnt_raw else None
        except ValueError:
            messagebox.showerror("Lỗi", "Thời gian và số lượng câu hỏi phải là số nguyên hợp lệ!")
            return

        def on_exam_created(res):
            exam = res.get("exam", {})
            messagebox.showinfo("Thành công", f"Đã tạo và kích hoạt kỳ thi #{exam.get('id')}:\n{exam.get('title')}")
            load_all_data()

        request(
            "exam.create",
            on_exam_created,
            bank_id=selected_bank["id"],
            title=exam_title,
            duration_minutes=dur,
            question_count=q_cnt,
            shuffle=var_shuffle.get(),
        )

    btn_create_exam = ctk.CTkButton(
        left_cfg,
        text="🚀 Tạo & Kích Hoạt Kỳ Thi Này",
        height=36,
        fg_color=CyberpunkTheme.PURPLE,
        font=ctk.CTkFont(weight="bold"),
        command=on_create_exam,
    )
    btn_create_exam.pack(fill="x", padx=16, pady=(0, 12))

    # --- KHUNG HIỂN THỊ KỲ THI HIỆN TẠI VÀ ĐIỀU KHIỂN BẮT ĐẦU/KẾT THÚC ---
    active_box = ctk.CTkFrame(left_cfg, fg_color=CyberpunkTheme.PANEL_BORDER, corner_radius=8)
    active_box.pack(fill="x", padx=16, pady=(0, 14))

    lbl_active_title = ctk.CTkLabel(
        active_box,
        text="Trạng thái kỳ thi: Đang tải...",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=CyberpunkTheme.CYAN,
        wraplength=360,
        justify="left",
    )
    lbl_active_title.pack(anchor="w", padx=10, pady=(8, 4))

    lbl_active_status = ctk.CTkLabel(
        active_box,
        text="Trạng thái: Chưa bắt đầu",
        font=ctk.CTkFont(size=11),
        text_color=CyberpunkTheme.TEXT_MUTED,
    )
    lbl_active_status.pack(anchor="w", padx=10, pady=(0, 8))

    btn_ctrl_row = ctk.CTkFrame(active_box, fg_color="transparent")
    btn_ctrl_row.pack(fill="x", padx=10, pady=(0, 8))

    def set_exam_status(new_status: str):
        def on_st_updated(res):
            messagebox.showinfo("Thông báo", f"Đã chuyển trạng thái kỳ thi sang: {new_status}")
            load_all_data()

        request("exam.status.set", on_st_updated, status=new_status)

    btn_start_exam = ctk.CTkButton(
        btn_ctrl_row,
        text="▶ Bắt Đầu Thi",
        fg_color=CyberpunkTheme.GREEN,
        width=160,
        command=lambda: set_exam_status("IN_PROGRESS"),
    )
    btn_start_exam.pack(side="left", padx=(0, 4))

    btn_stop_exam = ctk.CTkButton(
        btn_ctrl_row,
        text="⏹ Kết Thúc Thi",
        fg_color=CyberpunkTheme.RED,
        width=160,
        command=lambda: set_exam_status("FINISHED"),
    )
    btn_stop_exam.pack(side="right", padx=(4, 0))

    # --- KHUNG 3: THIẾT LẬP QUY CHẾ ĐIỂM PHẠT ---
    ctk.CTkLabel(
        left_cfg,
        text="2. Quy Chế Điểm Phạt & Vi Phạm",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=15, weight="bold"),
        text_color=CyberpunkTheme.TEXT_WHITE,
    ).pack(anchor="w", padx=16, pady=(10, 8))

    ctk.CTkLabel(left_cfg, text="Điểm ban đầu (thang điểm):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_init_score = ctk.CTkEntry(left_cfg)
    entry_init_score.pack(fill="x", padx=16, pady=(0, 8))
    entry_init_score.insert(0, "10.0")

    ctk.CTkLabel(left_cfg, text="Mức trừ điểm / mỗi lần vi phạm:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_penalty = ctk.CTkEntry(left_cfg)
    entry_penalty.pack(fill="x", padx=16, pady=(0, 8))
    entry_penalty.insert(0, "1.0")

    ctk.CTkLabel(left_cfg, text="Số lần vi phạm tối đa (bị khóa bài):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(4, 2))
    entry_max_viol = ctk.CTkEntry(left_cfg)
    entry_max_viol.pack(fill="x", padx=16, pady=(0, 12))
    entry_max_viol.insert(0, "3")

    def save_configuration():
        try:
            cfg = {
                "initial_score": float(entry_init_score.get().strip()),
                "penalty_per_violation": float(entry_penalty.get().strip()),
                "max_violations": int(entry_max_viol.get().strip()),
                "duration_minutes": int(entry_duration.get().strip()),
                "exam_title": entry_exam_name.get().strip(),
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
        text="💾 Áp Dụng Quy Chế Phạt",
        height=36,
        fg_color=CyberpunkTheme.PURPLE,
        font=ctk.CTkFont(weight="bold"),
        command=save_configuration,
    )
    btn_save_cfg.pack(fill="x", padx=16, pady=(0, 20))

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

    def on_banks(res):
        nonlocal bank_items
        bank_items = res.get("banks", [])
        if bank_items:
            values = []
            values.append("🎲 [RANDOM ĐỀ] Bốc ngẫu nhiên đề cho mỗi học sinh")
            for b in bank_items:
                values.append(f"#{b['id']} - {b['title']} ({b.get('question_count', 0)} câu)")
            combo_banks.configure(values=values)
            if combo_banks.get() not in values:
                combo_banks.set(values[0])
        else:
            combo_banks.configure(values=["-- Chưa có ngân hàng đề nào (Hãy bấm Nhập đề) --"])
            combo_banks.set("-- Chưa có ngân hàng đề nào (Hãy bấm Nhập đề) --")

    def on_banks_err(err):
        combo_banks.configure(values=["-- ⚠️ Chưa kết nối Server (Bấm Làm mới) --"])
        combo_banks.set("-- ⚠️ Chưa kết nối Server (Bấm Làm mới) --")

    def load_banks_only():
        combo_banks.configure(values=["-- Đang tải ngân hàng đề... --"])
        combo_banks.set("-- Đang tải ngân hàng đề... --")
        request("exam.banks.list", on_banks, on_error=on_banks_err)

    def load_all_data():
        load_banks_only()

        def on_active_exam(res):
            exam = res.get("exam")
            if exam:
                title = exam.get('title', '')
                is_rnd = title.startswith("[RANDOM]")
                mode_str = " (🎲 Random đề theo từng MSSV)" if is_rnd else ""
                lbl_active_title.configure(
                    text=f"Kỳ thi hiện tại: #{exam.get('id')} - {title}{mode_str}\nNgân hàng đề: {exam.get('bank_title', '')} | Thời gian: {exam.get('duration_minutes')}p"
                )
            else:
                lbl_active_title.configure(text="Chưa có kỳ thi nào được chọn (Hãy tạo kỳ thi ở trên)")

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
            st = str(cfg.get("status", "Chưa bắt đầu"))
            lbl_active_status.configure(text=f"Trạng thái hệ thống: {st}")

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

        request("exam.active.get", on_active_exam)
        request("exam.config.get", on_cfg)
        request("exam.students.list", on_students)

    frame.load_data = load_all_data
    frame.after(600, load_all_data)
    return frame

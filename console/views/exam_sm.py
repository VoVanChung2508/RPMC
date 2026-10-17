from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from console.theme import CyberpunkTheme


def build_exam_sm(root, request):
    frame = ctk.CTkFrame(root, fg_color="transparent")

    # Header section
    header_box = ctk.CTkFrame(frame, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    header_box.pack(fill="x", padx=12, pady=(12, 8))

    ctk.CTkLabel(
        header_box,
        text="🛡️ SCRUM MASTER / GIÁM THỊ PHÒNG THI (REAL-TIME LAN MONITORING)",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=18, weight="bold"),
        text_color=CyberpunkTheme.CYAN,
    ).pack(side="left", padx=16, pady=12)

    auto_refresh_var = tk.BooleanVar(value=True)

    def toggle_auto_refresh():
        if auto_refresh_var.get():
            btn_auto.configure(text="Auto-Refresh: ON", fg_color=CyberpunkTheme.GREEN)
        else:
            btn_auto.configure(text="Auto-Refresh: OFF", fg_color=CyberpunkTheme.PANEL_BORDER)

    btn_auto = ctk.CTkButton(
        header_box,
        text="Auto-Refresh: ON",
        width=130,
        height=32,
        fg_color=CyberpunkTheme.GREEN,
        command=lambda: [auto_refresh_var.set(not auto_refresh_var.get()), toggle_auto_refresh()],
    )
    btn_auto.pack(side="right", padx=16, pady=12)

    btn_refresh = ctk.CTkButton(
        header_box,
        text="Làm Mới",
        width=100,
        height=32,
        fg_color=CyberpunkTheme.PURPLE,
        command=lambda: refresh_data(),
    )
    btn_refresh.pack(side="right", padx=6, pady=12)

    # Main split container
    main_split = ctk.CTkFrame(frame, fg_color="transparent")
    main_split.pack(fill="both", expand=True, padx=12, pady=4)

    # Left Column: Students List Table
    left_col = ctk.CTkFrame(main_split, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    left_col.pack(side="left", fill="both", expand=True, padx=(0, 6))

    ctk.CTkLabel(
        left_col,
        text="Danh Sách Thí Sinh Trong Mạng LAN",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=15, weight="bold"),
        text_color=CyberpunkTheme.TEXT_WHITE,
    ).pack(anchor="w", padx=16, pady=(12, 6))

    # Table Header
    tbl_hdr = ctk.CTkFrame(left_col, fg_color=CyberpunkTheme.PANEL_BORDER, height=30)
    tbl_hdr.pack(fill="x", padx=12, pady=(0, 4))
    ctk.CTkLabel(tbl_hdr, text="MSSV", width=90, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Họ và Tên", width=140, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="IP LAN", width=100, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Điểm", width=60, anchor="center", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Vi Phạm", width=70, anchor="center", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
    ctk.CTkLabel(tbl_hdr, text="Trạng Thái", width=90, anchor="center", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)

    students_scroll = ctk.CTkScrollableFrame(left_col, fg_color="transparent")
    students_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # Right Column: Intervention Controls & Real-time Alerts
    right_col = ctk.CTkFrame(main_split, width=420, fg_color=CyberpunkTheme.PANEL_BG, corner_radius=12)
    right_col.pack(side="right", fill="both", padx=(6, 0))
    right_col.pack_propagate(False)

    ctk.CTkLabel(
        right_col,
        text="Quyền Can Thiệp Giám Thị (Intervention)",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=15, weight="bold"),
        text_color=CyberpunkTheme.YELLOW,
    ).pack(anchor="w", padx=16, pady=(12, 8))

    # Intervention Form
    selected_stu_var = tk.StringVar(value="")
    stu_dropdown = ctk.CTkOptionMenu(
        right_col,
        variable=selected_stu_var,
        values=["(Chưa có thí sinh)"],
        width=380,
    )
    stu_dropdown.pack(padx=16, pady=4)

    msg_entry = ctk.CTkEntry(
        right_col,
        placeholder_text="Nhập tin nhắn cảnh báo gửi tới thí sinh...",
        width=380,
    )
    msg_entry.pack(padx=16, pady=6)

    def send_warning_to_student():
        sid = selected_stu_var.get().strip()
        msg = msg_entry.get().strip()
        if not sid or sid.startswith("("):
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một thí sinh!")
            return
        if not msg:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập tin nhắn cảnh báo!")
            return
        request("exam.student.warn", lambda r: [
            messagebox.showinfo("Thành công", f"Đã gửi cảnh báo tới thí sinh {sid}!"),
            refresh_data()
        ], student_id=sid, message=msg)

    btn_send_warn = ctk.CTkButton(
        right_col,
        text="📢 Gửi Cảnh Báo Trực Tiếp",
        fg_color=CyberpunkTheme.YELLOW,
        text_color="#000000",
        command=send_warning_to_student,
    )
    btn_send_warn.pack(padx=16, pady=4, fill="x")

    def manual_penalty_student():
        sid = selected_stu_var.get().strip()
        if not sid or sid.startswith("("):
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một thí sinh!")
            return
        if not messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn trừ điểm thủ công thí sinh {sid}?"):
            return
        request("exam.student.penalty", lambda r: [
            messagebox.showinfo("Thành công", f"Đã trừ điểm vi phạm của thí sinh {sid}!"),
            refresh_data()
        ], student_id=sid, reason="Giám thị phát hiện hành vi gian lận ngoài đời")

    btn_penalty = ctk.CTkButton(
        right_col,
        text="⚠️ Trừ Điểm Thủ Công (-1 lần vi phạm)",
        fg_color=CyberpunkTheme.PURPLE,
        command=manual_penalty_student,
    )
    btn_penalty.pack(padx=16, pady=4, fill="x")

    def lock_student_exam():
        sid = selected_stu_var.get().strip()
        if not sid or sid.startswith("("):
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một thí sinh!")
            return
        if not messagebox.askyesno("CẢNH BÁO", f"CƯỠNG CHẾ KHÓA BÀI THI của thí sinh {sid}?"):
            return
        request("exam.student.lock", lambda r: [
            messagebox.showinfo("Thành công", f"Đã khóa quyền làm bài của thí sinh {sid}!"),
            refresh_data()
        ], student_id=sid, reason="Giám thị đình chỉ quyền thi trực tiếp")

    btn_lock = ctk.CTkButton(
        right_col,
        text="🔒 Khóa Bài Thi Ngay Lập Tức",
        fg_color=CyberpunkTheme.RED,
        command=lock_student_exam,
    )
    btn_lock.pack(padx=16, pady=4, fill="x")

    # Real-time Violation Alerts Feed
    ctk.CTkLabel(
        right_col,
        text="Thông Báo Vi Phạm Tức Thời (Live Alerts)",
        font=ctk.CTkFont(family=CyberpunkTheme.FONT, size=14, weight="bold"),
        text_color=CyberpunkTheme.CYAN,
    ).pack(anchor="w", padx=16, pady=(16, 6))

    alerts_box = ctk.CTkTextbox(
        right_col,
        width=380,
        height=180,
        font=ctk.CTkFont(family="Consolas", size=11),
        fg_color="#0a0e14",
    )
    alerts_box.pack(padx=16, pady=(0, 12), fill="both", expand=True)

    seen_violations_count = [0]

    def render_students(students):
        for widget in students_scroll.winfo_children():
            widget.destroy()

        stu_ids = []
        total_violations = 0
        for s in students:
            sid = s.get("student_id", "")
            stu_ids.append(sid)
            name = s.get("name", "")
            ip = s.get("ip_address", "")
            score = s.get("score", 10.0)
            v_count = s.get("violation_count", 0)
            total_violations += v_count
            status = s.get("status", "")

            row = ctk.CTkFrame(students_scroll, fg_color="transparent", height=28)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=sid, width=90, anchor="w", text_color=CyberpunkTheme.CYAN).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=name, width=140, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=ip, width=100, anchor="w", text_color=CyberpunkTheme.TEXT_MUTED).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"{score:.1f}", width=60, anchor="center", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)

            v_color = CyberpunkTheme.RED if v_count > 0 else CyberpunkTheme.TEXT_MUTED
            ctk.CTkLabel(row, text=str(v_count), width=70, anchor="center", text_color=v_color).pack(side="left", padx=4)

            status_color = CyberpunkTheme.GREEN
            if status == "LOCKED":
                status_color = CyberpunkTheme.RED
            elif status == "WARNED":
                status_color = CyberpunkTheme.YELLOW
            elif status == "SUBMITTED":
                status_color = CyberpunkTheme.CYAN

            ctk.CTkLabel(row, text=status, width=90, anchor="center", text_color=status_color).pack(side="left", padx=4)

        if stu_ids:
            stu_dropdown.configure(values=stu_ids)
            if not selected_stu_var.get() or selected_stu_var.get() not in stu_ids:
                selected_stu_var.set(stu_ids[0])
        else:
            stu_dropdown.configure(values=["(Chưa có thí sinh)"])
            selected_stu_var.set("(Chưa có thí sinh)")

    def update_alerts_feed(entries):
        alerts_box.delete("1.0", "end")
        for e in entries:
            act = e.get("action", "")
            if act in ("VIOLATION_RECORDED", "FORCE_LOCK", "SEND_WARNING"):
                dt = e.get("iso_time", "")
                actor = e.get("actor", "")
                details = e.get("details", {})
                sid = details.get("student_id", actor)
                v_info = details.get("violation", {})
                event_name = v_info.get("event_type", act)
                msg = f"[{dt}] {sid} -> {event_name}: {v_info.get('detail', details.get('message', ''))}\n"
                alerts_box.insert("end", msg)
        alerts_box.see("end")

    def refresh_data():
        def on_students(res):
            students = res.get("students", [])
            render_students(students)

        def on_audit(res):
            entries = res.get("entries", [])
            update_alerts_feed(entries)

        request("exam.students.list", on_students)
        request("exam.audit.list", on_audit)

    def auto_refresh_loop():
        if auto_refresh_var.get():
            try:
                refresh_data()
            except Exception:
                pass
        frame.after(2500, auto_refresh_loop)

    frame.after(500, refresh_data)
    frame.after(3000, auto_refresh_loop)

    return frame

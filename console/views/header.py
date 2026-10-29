from __future__ import annotations

import customtkinter as ctk

from console.theme import CyberpunkTheme


def build_header(root, target_agent, on_connect, initial_token="", initial_host="127.0.0.1", auto_connect_var=None):
    frame = ctk.CTkFrame(root, corner_radius=12)
    title = ctk.CTkLabel(
        frame,
        text="RPMC Console | Bảng Quản Trị & Giám Sát Thi Trực Tuyến",
        font=("Segoe UI", 18, "bold"),
    )
    title.grid(row=0, column=0, columnspan=2, padx=16, pady=(10, 4), sticky="w")

    host = ctk.CTkEntry(frame, width=140, placeholder_text="Server host")
    host.insert(0, initial_host or "127.0.0.1")
    host.grid(row=1, column=0, padx=(16, 8), pady=(0, 10), sticky="w")

    token = ctk.CTkEntry(frame, width=220, show="*", placeholder_text="Console token")
    if initial_token:
        token.insert(0, initial_token)
    token.grid(row=1, column=1, padx=8, pady=(0, 10), sticky="w")

    target = ctk.CTkOptionMenu(
        frame,
        variable=target_agent,
        values=["(no agents)"],
        command=lambda _value: None,
        width=130,
    )
    target.configure(state="disabled")
    target.grid(row=1, column=2, padx=8, pady=(0, 10), sticky="w")

    connect = ctk.CTkButton(frame, text="Kết nối / Refresh", command=on_connect, width=130)
    connect.grid(row=1, column=3, padx=8, pady=(0, 10), sticky="w")

    if auto_connect_var is not None:
        chk_auto = ctk.CTkCheckBox(frame, text="Tự kết nối", variable=auto_connect_var, width=95)
        chk_auto.grid(row=1, column=4, padx=8, pady=(0, 10), sticky="w")
        status_col = 5
    else:
        status_col = 4

    status = ctk.CTkLabel(
        frame,
        text="Sẵn sàng · Khởi động Server rồi bấm Kết nối",
        text_color=CyberpunkTheme.MUTED,
        anchor="w",
    )
    status.grid(row=1, column=status_col, padx=(8, 16), pady=(0, 10), sticky="ew")

    for column, weight in ((0, 1), (status_col, 1)):
        frame.grid_columnconfigure(column, weight=weight)
    return frame, host, token, target, status

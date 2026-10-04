from __future__ import annotations

import customtkinter as ctk

from console.theme import CyberpunkTheme


def build_header(root, target_agent, on_connect, initial_token=""):
    frame = ctk.CTkFrame(root, corner_radius=12)
    title = ctk.CTkLabel(
        frame,
        text="RPMC Console | Secure Remote Administration Platform",
        font=("Segoe UI", 18, "bold"),
    )
    title.grid(row=0, column=0, padx=16, pady=(10, 4), sticky="w")

    host = ctk.CTkEntry(frame, width=150, placeholder_text="Server host")
    host.insert(0, "127.0.0.1")
    host.grid(row=1, column=0, padx=(16, 8), pady=(0, 10), sticky="w")

    token = ctk.CTkEntry(frame, width=240, show="*", placeholder_text="Console token")
    if initial_token:
        token.insert(0, initial_token)
    token.grid(row=1, column=1, padx=8, pady=(0, 10), sticky="w")

    target = ctk.CTkOptionMenu(
        frame,
        variable=target_agent,
        values=["(no agents)"],
        command=lambda _value: None,
    )
    target.configure(state="disabled")
    target.grid(row=1, column=2, padx=8, pady=(0, 10), sticky="w")

    connect = ctk.CTkButton(frame, text="Refresh Agents", command=on_connect, width=130)
    connect.grid(row=1, column=3, padx=8, pady=(0, 10), sticky="w")

    status = ctk.CTkLabel(
        frame,
        text="Local demo · Start server and agent, then enter the console token",
        text_color=CyberpunkTheme.MUTED,
        anchor="w",
    )
    status.grid(row=1, column=4, padx=(8, 16), pady=(0, 10), sticky="ew")

    for column, weight in ((0, 1), (4, 1)):
        frame.grid_columnconfigure(column, weight=weight)
    return frame, host, token, target, status

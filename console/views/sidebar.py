from __future__ import annotations

import customtkinter as ctk


def build_sidebar(root, on_select):
    frame = ctk.CTkFrame(root, width=190, corner_radius=12)
    frame.pack_propagate(False)
    for name in (
        "Dashboard",
        "Clients",
        "Processes",
        "Files",
        "Screen Stream",
        "SOC Terminal",
        "Audit Log",
    ):
        ctk.CTkButton(
            frame,
            text=name,
            height=38,
            corner_radius=10,
            command=lambda page=name: on_select(page),
        ).pack(padx=12, pady=(8, 0), fill="x")
    return frame

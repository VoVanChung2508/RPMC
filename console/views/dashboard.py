from __future__ import annotations

import json

import customtkinter as ctk


def build_dashboard(root, request):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="System Dashboard", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    ctk.CTkLabel(
        frame,
        text="Live telemetry is collected from the selected, authenticated agent.",
        text_color="#94A3B8",
    ).pack(padx=16, anchor="w")
    output = ctk.CTkTextbox(frame, font=("Consolas", 13))
    output.pack(padx=16, pady=12, fill="both", expand=True)
    output.insert("end", "Select an agent above and refresh telemetry.\n")
    output.configure(state="disabled")
    state = {"live": False, "after_id": None}
    status = ctk.CTkLabel(frame, text="Snapshot mode", text_color="#94A3B8")
    status.pack(padx=16, pady=(0, 8), anchor="w")

    def show(data):
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("end", json.dumps(data, indent=2))
        output.configure(state="disabled")
        if state["live"]:
            status.configure(
                text=(
                    f"Live · CPU {data.get('cpu_percent', 0):.1f}% · "
                    f"RAM {data.get('used_ram_bytes', 0) / (1024 ** 3):.2f}/"
                    f"{data.get('total_ram_bytes', 0) / (1024 ** 3):.2f} GiB"
                )
            )
            state["after_id"] = frame.after(2000, refresh)

    def refresh():
        if state["live"]:
            request("system.info", show)

    def toggle_live():
        state["live"] = not state["live"]
        live_button.configure(
            text="Stop Live Telemetry" if state["live"] else "Start Live Telemetry"
        )
        status.configure(text="Refreshing..." if state["live"] else "Snapshot mode")
        if state["live"]:
            refresh()
        elif state["after_id"] is not None:
            frame.after_cancel(state["after_id"])
            state["after_id"] = None

    ctk.CTkButton(
        frame,
        text="Refresh System Information",
        command=lambda: request("system.info", show),
    ).pack(padx=16, pady=(0, 8), anchor="w")
    live_button = ctk.CTkButton(
        frame,
        text="Start Live Telemetry",
        command=toggle_live,
    )
    live_button.pack(padx=16, pady=(0, 16), anchor="w")
    return frame

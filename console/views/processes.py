from __future__ import annotations

import json
from tkinter import messagebox

import customtkinter as ctk


def build_processes(root, request):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="Remote Process Manager", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    controls = ctk.CTkFrame(frame, fg_color="transparent")
    controls.pack(fill="x", padx=16)
    fetch_button = ctk.CTkButton(
        controls,
        text="Fetch Process List",
        command=lambda: request("process.list", show),
    )
    fetch_button.pack(side="left", padx=(0, 8))
    live = {"enabled": False, "after_id": None, "last_count": 0}
    live_status = ctk.CTkLabel(controls, text="Snapshot mode")
    live_status.pack(side="left", padx=8)
    pid_entry = ctk.CTkEntry(controls, placeholder_text="PID to terminate")
    pid_entry.pack(side="left", fill="x", expand=True, padx=8)
    output = ctk.CTkTextbox(frame, font=("Consolas", 12))
    output.pack(padx=16, pady=12, fill="both", expand=True)

    def show(data):
        processes = data if isinstance(data, list) else data.get("processes", [])
        live["last_count"] = len(processes)
        output.delete("1.0", "end")
        output.insert(
            "end",
            "PID\tUSER\tCPU%\tMEMORY\tNAME\n"
            + "\n".join(
                f"{p.get('pid')}\t{p.get('user')}\t{p.get('cpu_usage_percent', 0):.1f}"
                f"\t{p.get('memory_bytes', 0)}\t{p.get('name')}"
                for p in processes
            ),
        )
        if live["enabled"]:
            live_status.configure(text=f"Live · {len(processes)} processes · refreshing every 2 s")
            live["after_id"] = frame.after(2000, refresh_live)

    def refresh_live():
        if live["enabled"]:
            request("process.list", show)

    def toggle_live():
        live["enabled"] = not live["enabled"]
        live_button.configure(text="Stop Live" if live["enabled"] else "Start Live")
        live_status.configure(text="Starting live refresh..." if live["enabled"] else "Snapshot mode")
        if live["enabled"]:
            refresh_live()
        elif live["after_id"] is not None:
            frame.after_cancel(live["after_id"])
            live["after_id"] = None

    def terminate():
        try:
            pid = int(pid_entry.get())
            if pid <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid PID", "Enter a positive process ID.")
            return
        if not messagebox.askyesno(
            "Confirm process termination",
            f"Request termination of PID {pid}? The agent must also have termination enabled.",
        ):
            return
        request("process.terminate", lambda data: show_result(data), pid=pid)

    def show_result(data):
        output.insert("1.0", f"Termination result: {json.dumps(data)}\n")

    live_button = ctk.CTkButton(
        controls,
        text="Start Live",
        command=toggle_live,
    )
    live_button.pack(side="left", padx=8)
    ctk.CTkButton(
        controls,
        text="Terminate (requires agent opt-in)",
        fg_color="#991B1B",
        hover_color="#7F1D1D",
        command=terminate,
    ).pack(side="left", padx=(8, 0))
    return frame

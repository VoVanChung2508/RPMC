from __future__ import annotations

import json

import customtkinter as ctk


def build_clients(root, request):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="Connected Agents", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    output = ctk.CTkTextbox(frame, font=("Consolas", 13))
    output.pack(padx=16, pady=12, fill="both", expand=True)
    output.insert("end", "No live agent list loaded.\n")
    output.configure(state="disabled")

    def show(data):
        output.configure(state="normal")
        output.delete("1.0", "end")
        clients = data.get("clients", [])
        output.insert("end", json.dumps(clients, indent=2) if clients else "No agents are connected.")
        output.configure(state="disabled")

    ctk.CTkButton(
        frame, text="Refresh Connected Agents", command=lambda: request("client.list", show)
    ).pack(padx=16, pady=(0, 16), anchor="w")
    return frame

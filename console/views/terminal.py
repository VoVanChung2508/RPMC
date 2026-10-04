from __future__ import annotations

import json

import customtkinter as ctk


def build_terminal(root, request):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="SOC Operations Terminal", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    output = ctk.CTkTextbox(frame, font=("Consolas", 12))
    output.pack(padx=16, pady=12, fill="both", expand=True)
    output.insert(
        "end",
        "RPMC operations console. This is not an OS shell.\n"
        "Commands: help, system.info, client.list, process.list, audit.verify\n",
    )
    controls = ctk.CTkFrame(frame, fg_color="transparent")
    controls.pack(fill="x", padx=16, pady=(0, 16))
    entry = ctk.CTkEntry(controls, placeholder_text="Enter an RPMC operation")
    entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def execute(_event=None):
        command = entry.get().strip().lower()
        entry.delete(0, "end")
        output.insert("end", f"\nRPMC> {command}\n")
        operations = {
            "system.info": "system.info",
            "client.list": "client.list",
            "process.list": "process.list",
            "audit.verify": "audit.verify",
        }
        if command == "help":
            output.insert("end", "Allowed: help, system.info, client.list, process.list, audit.verify\n")
        elif command == "clear":
            output.delete("1.0", "end")
        elif command in operations:
            request(operations[command], lambda result: output.insert("end", json.dumps(result, indent=2) + "\n"))
        else:
            output.insert("end", "Unsupported operation. Arbitrary shell commands are disabled.\n")

    entry.bind("<Return>", execute)
    ctk.CTkButton(controls, text="Run Operation", command=execute).pack(side="left")
    return frame

from __future__ import annotations

import json

import customtkinter as ctk


def build_audit(root, request):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="Tamper-Evident Audit Log", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    controls = ctk.CTkFrame(frame, fg_color="transparent")
    controls.pack(fill="x", padx=16)
    output = ctk.CTkTextbox(frame, font=("Consolas", 11))
    output.pack(padx=16, pady=12, fill="both", expand=True)

    def show_entries(data):
        output.delete("1.0", "end")
        entries = data.get("entries", [])
        output.insert("end", "\n".join(json.dumps(item, sort_keys=True) for item in entries))
        if not entries:
            output.insert("end", "No audit entries yet.")

    def show_verify(data):
        output.insert("1.0", f"Integrity: {'VERIFIED' if data.get('valid') else 'FAILED'}\n{data.get('message')}\n\n")

    ctk.CTkButton(
        controls, text="Load Audit Entries", command=lambda: request("audit.list", show_entries)
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        controls, text="Verify Hash Chain", command=lambda: request("audit.verify", show_verify)
    ).pack(side="left")
    return frame

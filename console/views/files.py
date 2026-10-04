from __future__ import annotations

import base64
import os
from tkinter import filedialog, messagebox

import customtkinter as ctk


def build_files(root, request):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="Agent-Scoped File Browser", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    controls = ctk.CTkFrame(frame, fg_color="transparent")
    controls.pack(fill="x", padx=16)
    current_path = ctk.StringVar(value=".")
    selected_path = ctk.StringVar(value="")
    path_label = ctk.CTkLabel(controls, textvariable=current_path, anchor="w")
    path_label.pack(side="left", fill="x", expand=True)
    listing = ctk.CTkScrollableFrame(frame, label_text="Directory contents")
    listing.pack(padx=16, pady=12, fill="both", expand=True)
    status = ctk.CTkLabel(frame, text="Select an agent to browse its configured root.")
    status.pack(padx=16, pady=(0, 8), anchor="w")

    def show_files(data):
        for widget in listing.winfo_children():
            widget.destroy()
        items = data.get("files", [])
        selected_path.set("")
        for item in items:
            relative_path = item["path"]
            kind = "DIR " if item["is_dir"] else "FILE"
            label = f"{kind}  {item['name']}    {item['size']:,} bytes"

            def choose(path=relative_path, is_dir=item["is_dir"]):
                if is_dir:
                    current_path.set(path)
                    list_directory()
                else:
                    selected_path.set(path)
                    status.configure(text=f"Selected: {path}")

            ctk.CTkButton(
                listing,
                text=label,
                anchor="w",
                fg_color="transparent",
                hover_color="#1E293B",
                command=choose,
            ).pack(fill="x", padx=4, pady=2)
        status.configure(text=f"{len(items)} entries · root restricted · 8 MiB download limit")

    def list_directory():
        request("file.list", show_files, path=current_path.get())

    def go_up():
        parent = os.path.dirname(current_path.get().rstrip("\\/"))
        current_path.set(parent or ".")
        list_directory()

    def download():
        relative_path = selected_path.get()
        if not relative_path:
            messagebox.showerror("Select a file", "Select a file from the directory listing first.")
            return

        def save_result(data):
            destination = filedialog.asksaveasfilename(
                initialfile=data.get("name", os.path.basename(relative_path)),
                title="Save downloaded file",
            )
            if not destination:
                return
            try:
                contents = base64.b64decode(data["content_base64"], validate=True)
                if len(contents) != int(data["size"]):
                    raise ValueError("Downloaded file size does not match the server response")
                with open(destination, "wb") as handle:
                    handle.write(contents)
            except (KeyError, ValueError, OSError) as exc:
                messagebox.showerror("Download failed", str(exc))
                return
            status.configure(text=f"Saved {len(contents):,} bytes to {destination}")

        request("file.download", save_result, path=relative_path)

    ctk.CTkButton(controls, text="Up", width=72, command=go_up).pack(side="left", padx=6)
    ctk.CTkButton(controls, text="Refresh", command=list_directory).pack(side="left", padx=6)
    ctk.CTkButton(controls, text="Download Selected", command=download).pack(side="left", padx=6)
    return frame

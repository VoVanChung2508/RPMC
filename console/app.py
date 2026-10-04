from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from console.network import ConsoleNetworkClient
from console.theme import CyberpunkTheme
from console.views.audit import build_audit
from console.views.clients import build_clients
from console.views.dashboard import build_dashboard
from console.views.files import build_files
from console.views.header import build_header
from console.views.processes import build_processes
from console.views.screen import build_screen
from console.views.sidebar import build_sidebar
from console.views.terminal import build_terminal


class RPMCApp(ctk.CTk):
    AGENT_OPERATIONS = {
        "system.info",
        "process.list",
        "process.terminate",
        "file.list",
        "file.download",
        "screen.capture",
        "screen.stop",
    }

    def __init__(self):
        super().__init__()
        self.title("RPMC Console")
        self.geometry("1280x760")
        self.minsize(960, 640)
        self.configure(fg_color=CyberpunkTheme.BG)
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.target_agent = tk.StringVar(value="")
        self.pages: dict[str, ctk.CTkFrame] = {}
        self._screen_stop: threading.Event | None = None

        self.header, self.host_entry, self.token_entry, self.target_menu, self.status = build_header(
            self,
            self.target_agent,
            self.refresh_clients,
            os.environ.get("RPMC_ADMIN_TOKEN", ""),
        )
        self.header.pack(fill="x", padx=16, pady=(16, 8))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.sidebar = build_sidebar(body, self.show_page)
        self.sidebar.pack(side="left", fill="y", padx=(0, 12))

        self.page_host = ctk.CTkFrame(body, fg_color=CyberpunkTheme.BG)
        self.page_host.pack(side="right", fill="both", expand=True)
        request = self.request
        self.pages = {
            "Dashboard": build_dashboard(self.page_host, request),
            "Clients": build_clients(self.page_host, request),
            "Processes": build_processes(self.page_host, request),
            "Files": build_files(self.page_host, request),
            "Screen Stream": build_screen(self.page_host, request, self.stream_screen),
            "SOC Terminal": build_terminal(self.page_host, request),
            "Audit Log": build_audit(self.page_host, request),
        }
        for page in self.pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.show_page("Dashboard")
        self.after(250, self.refresh_clients)

    def show_page(self, name: str) -> None:
        page = self.pages.get(name)
        if page is not None:
            page.tkraise()

    def _close_window(self) -> None:
        if self._screen_stop is not None:
            self._screen_stop.set()
        self.destroy()

    def request(self, operation: str, callback=None, **fields) -> None:
        if operation in self.AGENT_OPERATIONS:
            client_id = self.target_agent.get().strip()
            if not client_id:
                self.status.configure(text="No agent selected — refresh Clients first", text_color=CyberpunkTheme.YELLOW)
                return
            fields["client_id"] = client_id

        host = self.host_entry.get().strip() or "127.0.0.1"
        token = self.token_entry.get()
        try:
            port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
        except ValueError:
            self.status.configure(text="RPMC_SERVER_PORT must be a number", text_color=CyberpunkTheme.RED)
            return
        actor = os.environ.get("USERNAME", "console")
        try:
            client = ConsoleNetworkClient(host, port, token, actor)
        except ValueError as exc:
            self.status.configure(text=str(exc), text_color=CyberpunkTheme.RED)
            return
        self.status.configure(text=f"Running {operation}...", text_color=CyberpunkTheme.YELLOW)

        def work():
            try:
                result = client.request(operation, **fields)
            except (OSError, ConnectionError, RuntimeError, ValueError, KeyError) as exc:
                self.after(0, lambda error=exc: self._request_failed(operation, error))
                return
            self.after(0, lambda: self._request_succeeded(operation, result, callback))

        threading.Thread(target=work, daemon=True).start()

    def _request_failed(self, operation: str, error: Exception) -> None:
        self.status.configure(text=f"{operation} failed: {error}", text_color=CyberpunkTheme.RED)

    def _request_succeeded(self, operation: str, result: dict, callback) -> None:
        self.status.configure(text=f"Connected · {operation} completed", text_color=CyberpunkTheme.GREEN)
        if operation == "client.list":
            clients = [item["client_id"] for item in result.get("clients", [])]
            self.target_menu.configure(values=clients or ["(no agents)"])
            if self.target_agent.get() not in clients:
                self.target_agent.set(clients[0] if clients else "")
            self.target_menu.configure(state="normal" if clients else "disabled")
        if callback is not None:
            callback(result)

    def refresh_clients(self) -> None:
        self.request("client.list")

    def stream_screen(self, on_frame, on_error) -> threading.Event | None:
        if self._screen_stop is not None and not self._screen_stop.is_set():
            return None
        client_id = self.target_agent.get().strip()
        if not client_id:
            self.status.configure(
                text="No agent selected — refresh Clients first",
                text_color=CyberpunkTheme.YELLOW,
            )
            return None
        host = self.host_entry.get().strip() or "127.0.0.1"
        token = self.token_entry.get()
        actor = os.environ.get("USERNAME", "console")
        try:
            port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
            client = ConsoleNetworkClient(host, port, token, actor)
        except ValueError as exc:
            self.status.configure(text=str(exc), text_color=CyberpunkTheme.RED)
            return None

        stop_event = threading.Event()
        self._screen_stop = stop_event
        self.status.configure(text="Opening persistent screen stream...", text_color=CyberpunkTheme.YELLOW)

        def work():
            try:
                client.stream_screen(
                    client_id,
                    stop_event,
                    lambda data: self.after(0, lambda payload=data: on_frame(payload)),
                )
            except (OSError, ConnectionError, RuntimeError, ValueError, KeyError) as exc:
                if not stop_event.is_set():
                    self.after(0, lambda error=exc: on_error(error))
            finally:
                stop_event.set()

        threading.Thread(target=work, daemon=True).start()
        return stop_event


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = RPMCApp()
    app.mainloop()


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# Đảm bảo nhận thư mục gốc dự án khi chạy file trực tiếp
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import customtkinter as ctk

from common.env import load_dotenv
from console.network import ConsoleNetworkClient
from console.theme import CyberpunkTheme
from console.views.audit import build_audit
from console.views.clients import build_clients
from console.views.dashboard import build_dashboard
from console.views.exam_po import build_exam_po
from console.views.exam_sm import build_exam_sm
from console.views.files import build_files
from console.views.header import build_header
from console.views.processes import build_processes
from console.views.screen import build_screen
from console.views.sidebar import build_sidebar
from console.views.terminal import build_terminal

SETTINGS_PATH = Path(project_root) / "console_settings.json"


def load_console_settings() -> dict:
    try:
        if SETTINGS_PATH.exists():
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_console_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# Main admin console window. It wires the UI pages to the network client and tracks the selected agent.
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
        load_dotenv()
        self.title("RPMC Console")
        self.geometry("1280x760")
        self.minsize(960, 640)
        self.configure(fg_color=CyberpunkTheme.BG)
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.target_agent = tk.StringVar(value="")
        self.pages: dict[str, ctk.CTkFrame] = {}
        self._screen_stop: threading.Event | None = None

        # Nạp cấu hình phiên làm việc gần nhất
        self.settings = load_console_settings()
        initial_host = self.settings.get("host", "127.0.0.1")
        self.current_role = self.settings.get("role", "SM: Giám Sát Thi")
        auto_connect_default = bool(self.settings.get("auto_connect", True))
        self.auto_connect_var = tk.BooleanVar(value=auto_connect_default)

        self.header, self.host_entry, self.token_entry, self.target_menu, self.status = build_header(
            self,
            self.target_agent,
            self.refresh_clients,
            os.environ.get("RPMC_ADMIN_TOKEN", ""),
            initial_host=initial_host,
            auto_connect_var=self.auto_connect_var,
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
            "SM: Giám Sát Thi": build_exam_sm(self.page_host, request),
            "PO: Quy Chế & Điểm": build_exam_po(self.page_host, request),
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

        # Mở tab tương ứng với vai trò đã lưu
        self.show_page(self.current_role)

        # Tự động kết nối nếu được bật
        self.after(250, self._maybe_auto_connect)

    def show_page(self, name: str) -> None:
        self.current_role = name
        page = self.pages.get(name)
        if page is not None:
            page.tkraise()
            if hasattr(page, "load_data"):
                self.after(50, page.load_data)

    def _maybe_auto_connect(self) -> None:
        host = self.host_entry.get().strip() or "127.0.0.1"
        token = self.token_entry.get().strip()
        if self.auto_connect_var.get() and token and host in ("127.0.0.1", "localhost", "0.0.0.0"):
            self.refresh_clients()

    def _save_current_settings(self) -> None:
        try:
            port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
        except ValueError:
            port = 8090
        settings = {
            "host": self.host_entry.get().strip() or "127.0.0.1",
            "port": port,
            "role": getattr(self, "current_role", "SM: Giám Sát Thi"),
            "auto_connect": self.auto_connect_var.get() if hasattr(self, "auto_connect_var") else True,
        }
        save_console_settings(settings)

    def _close_window(self) -> None:
        self._save_current_settings()
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
        self._save_current_settings()
        if operation == "client.list":
            clients = [item["client_id"] for item in result.get("clients", [])]
            self.target_menu.configure(values=clients or ["(no agents)"])
            if self.target_agent.get() not in clients:
                self.target_agent.set(clients[0] if clients else "")
            self.target_menu.configure(state="normal" if clients else "disabled")
            # Tự động làm mới dữ liệu trang hiện tại (ví dụ PO hoặc SM)
            current_page = self.pages.get(self.current_role)
            if current_page is not None and hasattr(current_page, "load_data"):
                self.after(50, current_page.load_data)
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

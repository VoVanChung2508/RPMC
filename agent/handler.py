from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path

from common.protocol import CommandType, Frame, FrameType
from agent.file_svc import FileService
from agent.policy import CommandPolicyEnforcer
from agent.process_svc import ProcessService
from agent.screen import ScreenCaptureService
from agent.system_svc import SystemService


class CommandHandler:
    def __init__(self, root_dir: str = ".", allow_termination: bool = False):
        self.system_service = SystemService()
        self.process_service = ProcessService(allow_termination=allow_termination)
        self.file_service = FileService(str(Path(root_dir).expanduser().resolve()))
        self.policy = CommandPolicyEnforcer()
        self.screen_service = ScreenCaptureService()

    def handle(self, frame: Frame) -> Frame:
        cmd = frame.command_type
        try:
            if not self.policy.is_allowed(cmd):
                raise PermissionError(f"Command {cmd.name} is disabled by local agent policy")
            if cmd == CommandType.SYSTEM_INFO_REQUEST:
                payload = asdict(self.system_service.get_system_info())
            elif cmd == CommandType.PROCESS_LIST_REQUEST:
                payload = {"processes": [asdict(item) for item in self.process_service.list_processes()]}
            elif cmd == CommandType.PROCESS_KILL_REQUEST:
                request = self._json(frame.payload)
                payload = {
                    "pid": int(request["pid"]),
                    "success": self.process_service.terminate_process(int(request["pid"])),
                }
            elif cmd == CommandType.FILE_LIST_REQUEST:
                request = self._json(frame.payload)
                payload = {"files": self.file_service.list_files(str(request.get("path", ".")))}
            elif cmd == CommandType.FILE_DOWNLOAD_REQUEST:
                request = self._json(frame.payload)
                relative_path = str(request["path"])
                contents = self.file_service.read_bytes(relative_path)
                payload = {
                    "path": relative_path,
                    "name": Path(relative_path).name,
                    "size": len(contents),
                    "content_base64": base64.b64encode(contents).decode("ascii"),
                }
                return Frame(
                    FrameType.DATA,
                    CommandType.FILE_CHUNK_DATA,
                    json.dumps(payload).encode("utf-8"),
                )
            elif cmd == CommandType.SCREEN_START_REQUEST:
                request = self._json(frame.payload)
                width, height, tiles = self.screen_service.capture_delta_tiles(
                    force_full=bool(request.get("force_full", False))
                )
                payload = {
                    "width": width,
                    "height": height,
                    "tiles": tiles,
                }
                return Frame(
                    FrameType.DATA,
                    CommandType.SCREEN_TILE_DATA,
                    json.dumps(payload).encode("utf-8"),
                )
            elif cmd == CommandType.SCREEN_STOP_REQUEST:
                self.screen_service.stop()
                payload = {"status": "STREAMING_STOPPED"}
            else:
                raise ValueError(f"Unsupported command: {cmd.name}")
            return Frame(
                FrameType.CONTROL,
                CommandType.GENERIC_RESPONSE,
                json.dumps(payload).encode("utf-8"),
            )
        except Exception as exc:
            return Frame(
                FrameType.CONTROL,
                CommandType.ERROR_RESPONSE,
                json.dumps({"error": type(exc).__name__, "message": str(exc)}).encode("utf-8"),
            )

    @staticmethod
    def _json(payload: bytes) -> dict:
        if not payload:
            return {}
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Request payload must be a JSON object")
        return value

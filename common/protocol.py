from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import List


class FrameType(IntEnum):
    CONTROL = 0x0001
    DATA = 0x0002
    HEARTBEAT = 0x0003
    CLOSE = 0x0004


class CommandType(IntEnum):
    AUTH_REQUEST = 0x0101
    AUTH_RESPONSE = 0x0102
    SESSION_HELLO = 0x0103
    SESSION_BIND_DATA = 0x0104
    HEARTBEAT_PING = 0x0105
    HEARTBEAT_PONG = 0x0106
    SYSTEM_INFO_REQUEST = 0x0201
    SYSTEM_INFO_RESPONSE = 0x0202
    SYSTEM_POWER_ACTION = 0x0203
    PROCESS_LIST_REQUEST = 0x0301
    PROCESS_LIST_RESPONSE = 0x0302
    PROCESS_KILL_REQUEST = 0x0303
    PROCESS_KILL_RESPONSE = 0x0304
    FILE_LIST_REQUEST = 0x0401
    FILE_LIST_RESPONSE = 0x0402
    FILE_DOWNLOAD_REQUEST = 0x0403
    FILE_DOWNLOAD_META = 0x0404
    FILE_UPLOAD_REQUEST = 0x0405
    FILE_CHUNK_DATA = 0x0406
    FILE_CHUNK_ACK = 0x0407
    FILE_DELETE_REQUEST = 0x0408
    SCREEN_START_REQUEST = 0x0501
    SCREEN_STOP_REQUEST = 0x0502
    SCREEN_TILE_DATA = 0x0503
    GENERIC_RESPONSE = 0x0901
    ERROR_RESPONSE = 0x0999


class ErrorCode(IntEnum):
    OK = 0x0000
    INVALID_REQUEST = 0x1001
    AUTH_FAILED = 0x1002
    ACCESS_DENIED = 0x1003
    PATH_INVALID = 0x1004
    PROCESS_NOT_FOUND = 0x1005
    INTERNAL_ERROR = 0x1999


@dataclass(frozen=True)
class Frame:
    frame_type: FrameType
    command_type: CommandType
    payload: bytes

    MAGIC_HEADER = 0x5352
    PROTOCOL_VERSION = 0x01
    HEADER_SIZE = 12
    MAX_PAYLOAD_SIZE = 16 * 1024 * 1024

    @property
    def payload_length(self) -> int:
        return len(self.payload)

    def to_bytes(self) -> bytes:
        if self.payload_length > self.MAX_PAYLOAD_SIZE:
            raise ValueError(f"Payload too large: {self.payload_length}")

        header = struct.pack(
            ">HBBIHH",
            self.MAGIC_HEADER,
            self.PROTOCOL_VERSION,
            0x00,
            self.payload_length,
            self.frame_type.value,
            self.command_type.value,
        )
        return header + self.payload


class FrameCodec:
    @staticmethod
    def encode(frame: Frame) -> bytes:
        return frame.to_bytes()

    @staticmethod
    def decode(data: bytes) -> Frame:
        if len(data) < Frame.HEADER_SIZE:
            raise ValueError("Frame is shorter than 12 bytes")

        magic, version, reserved, payload_len, frame_type_id, command_type_id = struct.unpack(
            ">HBBIHH", data[: Frame.HEADER_SIZE]
        )
        if magic != Frame.MAGIC_HEADER:
            raise ValueError(f"Invalid magic header: 0x{magic:04x}")
        if version != Frame.PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")
        if payload_len < 0 or payload_len > Frame.MAX_PAYLOAD_SIZE:
            raise ValueError(f"Illegal payload size: {payload_len}")
        if len(data) != Frame.HEADER_SIZE + payload_len:
            raise ValueError("Frame size does not match its payload length")

        payload = data[Frame.HEADER_SIZE : Frame.HEADER_SIZE + payload_len]
        return Frame(
            frame_type=FrameType(frame_type_id),
            command_type=CommandType(command_type_id),
            payload=payload,
        )

    @staticmethod
    def decode_buffer(buffer: bytes) -> List[Frame]:
        frames: List[Frame] = []
        offset = 0
        while offset + Frame.HEADER_SIZE <= len(buffer):
            header = buffer[offset : offset + Frame.HEADER_SIZE]
            _, _, _, payload_len, _, _ = struct.unpack(">HBBIHH", header)
            frame_end = offset + Frame.HEADER_SIZE + payload_len
            if frame_end > len(buffer):
                break
            frames.append(FrameCodec.decode(buffer[offset:frame_end]))
            offset = frame_end
        return frames

    @staticmethod
    def read_frame(sock) -> Frame:
        header = FrameCodec._read_exact(sock, Frame.HEADER_SIZE)
        magic, version, _, payload_len, _, _ = struct.unpack(">HBBIHH", header)
        if magic != Frame.MAGIC_HEADER:
            raise ValueError(f"Invalid magic header: 0x{magic:04x}")
        if version != Frame.PROTOCOL_VERSION:
            raise ValueError(f"Unsupported protocol version: {version}")
        if payload_len > Frame.MAX_PAYLOAD_SIZE:
            raise ValueError(f"Illegal payload size: {payload_len}")
        return FrameCodec.decode(header + FrameCodec._read_exact(sock, payload_len))

    @staticmethod
    def _read_exact(sock, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = sock.recv(size - len(chunks))
            if not chunk:
                raise ConnectionError("Connection closed before the frame was complete")
            chunks.extend(chunk)
        return bytes(chunks)

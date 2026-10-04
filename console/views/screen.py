from __future__ import annotations

import base64
import io

import customtkinter as ctk
from PIL import Image


def build_screen(root, request, open_stream):
    frame = ctk.CTkFrame(root, corner_radius=12)
    ctk.CTkLabel(frame, text="On-Demand Screen View", font=("Segoe UI", 20, "bold")).pack(
        padx=16, pady=(16, 8), anchor="w"
    )
    controls = ctk.CTkFrame(frame, fg_color="transparent")
    controls.pack(fill="x", padx=16)
    image_label = ctk.CTkLabel(frame, text="Screen capture is off")
    image_label.pack(padx=16, pady=12, fill="both", expand=True)
    status = ctk.CTkLabel(frame, text="Captures are requested only while streaming is enabled.")
    status.pack(padx=16, pady=(0, 12), anchor="w")
    state = {"streaming": False, "image": None, "preview": None, "stop_event": None}

    def update_image(data):
        if not state["streaming"]:
            return
        try:
            width, height = int(data["width"]), int(data["height"])
            image = state["image"]
            if image is None or image.size != (width, height):
                image = Image.new("RGB", (width, height), "#0f172a")
            tiles = data.get("tiles", [])
            for tile in tiles:
                raw = base64.b64decode(tile["jpeg_base64"], validate=True)
                with Image.open(io.BytesIO(raw)) as decoded:
                    image.paste(decoded.convert("RGB"), (int(tile["x"]), int(tile["y"])))
            state["image"] = image
            preview_image = image.copy()
            preview_image.thumbnail((1000, 600))
            preview = ctk.CTkImage(
                light_image=preview_image,
                dark_image=preview_image,
                size=preview_image.size,
            )
            state["preview"] = preview
            image_label.configure(image=preview, text="")
            status.configure(
                text=f"Live delta stream · {width} x {height} · {len(tiles)} changed tiles"
            )
        except (KeyError, ValueError, OSError) as exc:
            state["streaming"] = False
            status.configure(text=f"Could not display capture: {exc}")

    def stream_failed(error):
        state["streaming"] = False
        state["stop_event"] = None
        status.configure(text=f"Screen stream stopped: {error}")

    def start():
        if state["streaming"]:
            return
        state["streaming"] = True
        state["image"] = None
        state["preview"] = None
        status.configure(text="Opening persistent screen stream...")
        stop_event = open_stream(update_image, stream_failed)
        if stop_event is None:
            state["streaming"] = False
            status.configure(text="Could not start stream; check agent selection and connection.")
            return
        state["stop_event"] = stop_event

    def stop():
        state["streaming"] = False
        stop_event = state["stop_event"]
        if stop_event is not None:
            stop_event.set()
            state["stop_event"] = None
        request("screen.stop", lambda _data: None)
        image_label.configure(image=None, text="Screen capture is off")
        state["image"] = None
        state["preview"] = None
        status.configure(text="Screen capture stopped.")

    ctk.CTkButton(controls, text="Start Screen View", command=start).pack(side="left", padx=(0, 8))
    ctk.CTkButton(controls, text="Stop", command=stop).pack(side="left")
    return frame

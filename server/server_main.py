from __future__ import annotations

import os

from server.listener import ServerListener


def main() -> None:
    host = os.environ.get("RPMC_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("RPMC_SERVER_PORT", "8090"))
    listener = ServerListener(host=host, port=port)
    try:
        listener.start()
    except KeyboardInterrupt:
        print("Stopping RPMC server")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()

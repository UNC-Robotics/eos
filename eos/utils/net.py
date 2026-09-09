import socket


def is_port_in_use(host: str, port: int) -> bool:
    """Whether a TCP server would fail to bind to host:port because something already holds it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # Mirror how servers (Node/libuv, uvicorn) bind, so a port lingering in TIME_WAIT is not a false positive
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False

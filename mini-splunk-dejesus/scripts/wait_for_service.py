import socket
import time


def wait(host, port, timeout=120):

    start = time.time()

    while True:

        try:

            with socket.create_connection((host, port), timeout=2):
                return

        except OSError:

            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {host}:{port}")

            time.sleep(2)
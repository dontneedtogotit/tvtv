#!/usr/bin/env python3
"""Send a command to MPV via its IPC socket.

Two modes:
  mpv-ipc.py <socket> <command...>           raw text command (e.g. "cycle pause")
  mpv-ipc.py <socket> get_property <name>    JSON query, prints the value on success

Raw commands are fire-and-forget (socket closed after send). Property queries
read the reply and print the value, exiting non-zero on error.
"""
import json
import socket
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: mpv-ipc.py <socket_path> <command...> | get_property <name>",
              file=sys.stderr)
        sys.exit(1)

    socket_path = sys.argv[1]
    args = sys.argv[2:]

    # Property query: MPV JSON IPC request/response.
    if args[0] == "get_property" and len(args) >= 2:
        prop = args[1]
        payload = {"command": ["get_property", prop]}
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(socket_path)
            sock.sendall((json.dumps(payload) + "\n").encode())
            sock.settimeout(2.0)
            try:
                data = sock.recv(65536).decode()
            except socket.timeout:
                data = ""
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            sock.close()

        try:
            resp = json.loads(data)
        except Exception:
            print(f"Error: bad reply {data!r}", file=sys.stderr)
            sys.exit(1)
        if resp.get("error") == "success":
            print(resp.get("data", ""))
        else:
            print(f"Error: {resp.get('error')}", file=sys.stderr)
            sys.exit(1)
        return

    # Raw command (text protocol, fire-and-forget).
    command = " ".join(args)
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        sock.sendall((command + "\n").encode())
        sock.close()
        print(f"Sent: {command}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
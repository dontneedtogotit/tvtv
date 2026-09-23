#!/usr/bin/env python3
"""Send a single command to MPV via its IPC socket."""
import socket
import sys

def main():
    if len(sys.argv) < 3:
        print("Usage: mpv-ipc.py <socket_path> <command>")
        sys.exit(1)
    
    socket_path = sys.argv[1]
    command = " ".join(sys.argv[2:])
    
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

# main.py
import threading
import time
from multicast_listener import start_multicast_listener
from tcp_server import start_tcp_server

print("=== GATEWAY MINIMAL PROTOBUF ===")

threading.Thread(target=start_multicast_listener, daemon=True).start()
threading.Thread(target=start_tcp_server, daemon=True).start()

while True:
    time.sleep(1)

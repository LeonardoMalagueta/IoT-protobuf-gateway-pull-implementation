# tcp_server.py
import socket
import threading
from proto import smartcity_pb2
from device_manager import get_all_devices

TCP_PORT = 7000

def handle_client(conn, addr):
    print(f"[TCP] Cliente conectado: {addr}")

    while True:
        raw = conn.recv(4096)
        if not raw:
            break

        req = smartcity_pb2.GatewayRequest()
        try:
            req.ParseFromString(raw)
        except:
            continue

        if req.action == "LIST":
            resp = smartcity_pb2.GatewayResponse()
            resp.ok = True
            for d in get_all_devices():
                info = resp.devices.add()
                info.device_id = d["device_id"]
                info.device_type = d["device_type"]
                info.ip = d["ip"]
                info.port_udp = d["port_udp"]
                info.port_tcp = d["port_tcp"]
                info.last_value = 0.0
                info.last_seen = d["last_seen"]

            conn.sendall(resp.SerializeToString())

    conn.close()
    print(f"[TCP] Cliente desconectado: {addr}")


def start_tcp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("", TCP_PORT))
    sock.listen(5)

    print(f"[Gateway] TCP escutando na porta {TCP_PORT}")

    while True:
        conn, addr = sock.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

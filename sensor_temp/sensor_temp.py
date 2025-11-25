# sensor_temp.py
import socket
import time
import random
import threading
from proto import smartcity_pb2

MCAST_GRP = "224.1.1.1"
MCAST_PORT = 5007

GATEWAY_UDP_PORT = 6000  # o gateway mínimo usa essa porta
SENSOR_ID = "sensor_temp_001"
SENSOR_TYPE = "temperature"

def send_announce():
    """Envia announce via multicast (protobuf)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    msg = smartcity_pb2.DeviceAnnounce()
    msg.device_id = SENSOR_ID
    msg.device_type = SENSOR_TYPE
    msg.ip = socket.gethostbyname(socket.gethostname())
    msg.port_udp = 0  # esse sensor simples não escuta UDP
    msg.port_tcp = 0  # também não usa TCP

    while True:
        sock.sendto(msg.SerializeToString(), (MCAST_GRP, MCAST_PORT))
        print(f"[ANNOUNCE] enviado por {SENSOR_ID}")
        time.sleep(5)


def send_sensor_data():
    """Envia valores periódicos via UDP protobuf para o gateway."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        temp = round(20 + random.uniform(-3, 3), 2)

        msg = smartcity_pb2.SensorData()
        msg.device_id = SENSOR_ID
        msg.value = temp
        msg.timestamp = int(time.time())

        sock.sendto(msg.SerializeToString(), ("127.0.0.1", GATEWAY_UDP_PORT))
        print(f"[SENSOR_DATA] {SENSOR_ID} = {temp}")
        time.sleep(3)


# ============= MAIN ==============
if __name__ == "__main__":
    print(f"=== SENSOR TEMPERATURA: {SENSOR_ID} ===")

    threading.Thread(target=send_announce, daemon=True).start()
    threading.Thread(target=send_sensor_data, daemon=True).start()

    while True:
        time.sleep(1)

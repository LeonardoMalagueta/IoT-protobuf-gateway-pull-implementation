# device_manager.py
import time
from threading import Lock

devices = {}
lock = Lock()
#mudar essa função para apenas atualizar os dados de conexão e trabalhar em conjunto com o heatbeat para limpar a list na mesma taxa que atualiza (5s)
def update_device(device):                      #recebe um pacote do tipo anuncio de dispositivo
    with lock:
        devices[device.device_id] = {           #cria ou sobrescreve o device com o ID recebido
            "device_id": device.device_id,
            "device_type": device.device_type,
            "ip": device.ip,
            "port_udp": device.port_udp,
            "port_tcp": device.port_tcp,
            "last_seen": int(time.time()),
            "last_value": None
        }

def get_all_devices():
    with lock:
        return list(devices.values())


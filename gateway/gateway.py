import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import threading
import proto.projeto02_pb2 as proto
import dev_management as mng
import time

grupo_multicast = "224.1.1.1" #endereço genérico onde qualquer um pode ler ou escrever, os sensores vao escrever nele também
porta_multicast = 5007        #porta registrada arbitraria (entre   1024 e ++)
porta_unicast_udp = 6000        # onde  o gateway escuta dados de sensores (UDP)
TCP_PORT = 7000               # porta TCP para clients

devices = {}
devices_lock = threading.Lock()

def start_gateway():

    # THREAD 1 — envia discovery periódica (multicast)
    t1 = threading.Thread(
        target=mng.send_discover_loop,
        args=(grupo_multicast, porta_multicast, porta_unicast_udp),
        daemon=True
    )

    # THREAD 2 — escuta respostas dos sensores/atuadores
    t2 = threading.Thread(
        target=mng.listen_device,
        args=(porta_unicast_udp,devices,devices_lock),
        daemon=True
    )

    t1.start()
    t2.start()

    print("\n[GATEWAY] Descobrindo sensores em:",grupo_multicast,":",porta_multicast,"!\n")
    
    # loop principal do gateway (pode botar TCP aqui depois)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    start_gateway()

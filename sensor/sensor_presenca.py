import sys
import os

# Permite importar o módulo protobuf gerado
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import struct
import threading
import time
import random  # para simular presença
import proto.projeto02_pb2 as proto

GRUPO = "224.1.1.1"         # IP do grupo multicast
PORTA_GRUPO = 5007          # Porta do grupo multicast
MEU_ID = "SP01"             # ID do sensor de presença
MEU_TIPO = "presenca"       # tipo do dispositivo (vai aparecer na lista)
MEU_PORTA = 5012            # porta unicast UDP para falar com o gateway

gateway_addr = None
gateway_port = None


# ------------------------------------------------------------
# THREAD 1 — ESCUTAR DISCOVERY DO GATEWAY (MULTICAST)
# ------------------------------------------------------------
def escutar_discovery():
    global gateway_addr, gateway_port

    # Descobrir IP local
    socket_ip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        socket_ip.connect(('10.255.255.255', 1))
        IP = socket_ip.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        socket_ip.close()

    # Socket para ouvir multicast
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORTA_GRUPO))

    mreq = struct.pack("4sl", socket.inet_aton(GRUPO), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print("[SP] Aguardando DISCOVERY do gateway...")

    while True:
        data, addr = sock.recvfrom(4096)
        msg = proto.Descoberta()

        try:
            msg.ParseFromString(data)
        except:
            continue

        if msg.inicia_descoberta:
            print("[SP] DISCOVERY recebido do gateway:", addr)

            gateway_addr = addr[0]
            gateway_port = msg.porta_resposta

            # Monta resposta de anúncio como SENSOR
            resposta = proto.Resposta()
            sensor = resposta.sensor
            sensor.tipo = MEU_TIPO
            sensor.id = MEU_ID
            sensor.ip = IP
            sensor.porta = MEU_PORTA

            sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
            print("[SP] Anúncio de SENSOR DE PRESENÇA enviado ao gateway.")


# ------------------------------------------------------------
# THREAD 2 — ENVIAR LEITURAS (0 ou 1) PARA O GATEWAY (UDP)
# ------------------------------------------------------------
def enviar_leituras():
    global gateway_addr, gateway_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        if gateway_addr is None:
            time.sleep(1)
            continue

        # Simulação simples:
        #  - 80% do tempo: ausência (0.0)
        #  - 20% do tempo: presença (1.0)
        valor = 1.0 if random.random() < 0.2 else 0.0

        resposta = proto.Resposta()
        leitura = resposta.leitura
        leitura.id = MEU_ID
        leitura.valor = valor
        leitura.timestamp = int(time.time())

        sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
        estado = "PRESENÇA DETECTADA" if valor > 0 else "sem presença"
        print(f"[SP] Enviando leitura → {gateway_addr}:{gateway_port} | valor={valor} ({estado})")

        time.sleep(2)  # período entre leituras (ajuste como quiser)


# ------------------------------------------------------------
# MAIN — INICIAR THREADS
# ------------------------------------------------------------
if __name__ == "__main__":
    t1 = threading.Thread(target=escutar_discovery, daemon=True)
    t2 = threading.Thread(target=enviar_leituras, daemon=True)

    t1.start()
    t2.start()

    while True:
        time.sleep(1)

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import struct
import threading
import time
import proto.projeto02_pb2 as proto

GRUPO = "224.1.1.1"         #ip do grupo multicast definido
PORTA_GRUPO = 5007          #porta do grupo multicast (igual)
MEU_ID = "ST01"             #Identificador dele lá na lista
MEU_TIPO = "temperatura"    #tipo do dispositivo padroinzado
MEU_PORTA = 5008            #porta unicast do dispositivo (diferente)

# Essas variáveis vão guardar para onde enviar leituras
gateway_addr = None         # IP do gateway (descoberto no discovery)
gateway_port = None         # porta unicast do gateway (vem no discovery)


# ------------------------------------------------------------
# THREAD 1 — ESCUTAR DISCOVERY MULTICAST
# ------------------------------------------------------------
def escutar_discovery():
    global gateway_addr, gateway_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORTA_GRUPO))

    # entra no grupo multicast
    mreq = struct.pack("4sl", socket.inet_aton(GRUPO), socket.INADDR_ANY) #inet envia o ip em formato binário que o socket usa, inaddr é a constante 0.0.0.0 
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)    #Adesão ao grupo multicast das informacoes no pacote mreq

    print("[SENSOR] esperando DISCOVERY...")

    while True:
        data, addr = sock.recvfrom(4096)    #recebe os dados e o endereço do sender diferente do recv(), com buffer de 4096bytes
        msg = proto.Descoberta()            #cria o protoobjeto

        try:
            msg.ParseFromString(data)       #desserializa
        except:
            continue

        if msg.inicia_descoberta == True:
            print("[SENSOR] Recebi DISCOVERY:", msg)

            # salva a porta unicast do gateway
            gateway_addr = addr[0]
            gateway_port = msg.porta_resposta

            # monta resposta de anúncio
            resposta = proto.Resposta()
            s = resposta.sensor              # oneof tipo = sensor
            s.tipo = MEU_TIPO
            s.id = MEU_ID
            s.ip = "127.0.0.1"
            s.porta = MEU_PORTA

            # envia anúncio para o gateway via unicast
            sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
            print("[SENSOR] respondi ao gateway.")



# ------------------------------------------------------------
# THREAD 2 — ENVIAR LEITURAS PERIODICAMENTE
# ------------------------------------------------------------
def enviar_leituras():
    global gateway_addr, gateway_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        # ainda não recebeu discovery → não sabe para onde enviar
        if gateway_addr is None:
            time.sleep(1)
            continue

        resposta = proto.Resposta()
        leitura = resposta.leitura    # <-- usa exatamente o nome do .proto

        # dados da leitura
        leitura.id = MEU_ID
        leitura.valor = 20.5          # valor fake por enquanto
        leitura.timestamp = int(time.time())

        sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
        print(f"[SENSOR] enviando LEITURA → {gateway_addr}:{gateway_port}")

        time.sleep(2) # intervalo entre leituras

# ------------------------------------------------------------
# THREAD 3 — RECEBER COMANDOS VIA
# ------------------------------------------------------------



# ------------------------------------------------------------
# MAIN — INICIAR THREADS
# ------------------------------------------------------------
t1 = threading.Thread(target=escutar_discovery, daemon=True)
t2 = threading.Thread(target=enviar_leituras, daemon=True)

t1.start()
t2.start()

while True:
    time.sleep(1)

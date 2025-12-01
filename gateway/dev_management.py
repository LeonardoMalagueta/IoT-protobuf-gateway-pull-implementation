import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import time
import proto.projeto02_pb2 as proto

#O sensor que vai responder já sabe qual o grupo do multicast pois ele já ta escutando nele, mas a gente manda a porta unicast pra ele responder
#e isso ele nao sabe. assim ele nao precisa responder no multicast..

#================================== Scan da rede atras de devices ===============================
def send_discover_loop(grupo_multicast, porta_multicast, porta_unicast_udp):
    socket_udp_multi = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    discover_msg = proto.Descoberta()
    discover_msg.inicia_descoberta = True
    discover_msg.porta_resposta = porta_unicast_udp
    
    data = discover_msg.SerializeToString()

    while True:
        try:
            socket_udp_multi.sendto(data, (grupo_multicast, porta_multicast))   #Método ideal para envios multicast é o sendto e nao send pq estamos em uma rede multicast
        except Exception as e:
            print("[DEV_MNG_DISC] Erro ao enviar discover:", e)
        time.sleep(10)  # 10 segundos entre um anuncio e outro: >>>> PODE MODIFICAR TEMPO AQUI <<<<<



#================== ESCUTAS NA REDE UDP ====================
def listen_device(porta_unicast_udp, devices, devices_lock):
    #============================= CONFIG DO SOCKET E  RECEBIMENTO DA MENSAGEM ===============================
    socket_udp_uni = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_udp_uni.bind(('', porta_unicast_udp))
    
    print("[DEV_MNG] escutando respostas UNICAST em", porta_unicast_udp)

    while True:
        data, addr = socket_udp_uni.recvfrom(4096)  #receber os dados
        resposta = proto.Resposta()                 #criar a estrutura que vai receber os dados

        try:
            resposta.ParseFromString(data)          #desserializacao na estrutura criada, obtendo um objeto tipo protobuf
        except Exception as e:
            print("[DEV_MNG]Mensagem inválida recebida:", e)
            continue
        # o oneof que foi preenchido pra definir qual tipo de mensagem eu to recebendo
        tipo_msg = resposta.WhichOneof("tipo")
    #=========================================================================================================
    #============================== MENSAGEM DO TIPO ANNOUNCE DO SENSOR ======================================
        if tipo_msg == "sensor":
            sensor = resposta.sensor

            print(f"[DEV_MNG]Recebido anuncio de um sensor: {sensor.id} ({sensor.tipo}) IP={sensor.ip}:{sensor.porta}")

            # atualizar dicionário de dispositivos
            with devices_lock:
                devices[sensor.id] = {
                    "tipo": sensor.tipo,
                    "ip": sensor.ip,
                    "porta": sensor.porta,
                    "estado": None    # sensores não têm estado
                }
            print("[DEV_MNG] devices =", devices)
    #=========================================================================================================
    #================================== MENSAGEM DO TIPO ANNOUNCE DO ATUADOR =================================
        elif tipo_msg == "atuador":
            atuador = resposta.atuador

            print(f"[DEV_MNG]Recebido anuncio de um Atuador: {atuador.id} ({atuador.tipo}) IP={atuador.ip}:{atuador.porta} estado_inicial={atuador.estado_inicial}")

            with devices_lock:
                devices[atuador.id] = {
                    "tipo": atuador.tipo,
                    "ip": atuador.ip,
                    "porta": atuador.porta,
                    "estado": atuador.estado_inicial
                }
            print("[DEV_MNG] devices =", devices)
    #=========================================================================================================
    #==================================== MENSAGEM DO TIPO LEITURA ===========================================
        elif tipo_msg == "leitura":
            leitura = resposta.leitura

            print(f"[DEV_MNG]Leitura do sensor {leitura.id} recebida: valor={leitura.valor} timestamp={leitura.timestamp}")

            # Aqui você pode salvar leitura, atualizar banco, etc.
            # Exemplo: salvar última leitura dentro do dict
            with devices_lock:
                if leitura.id in devices:
                    devices[leitura.id]["ultima_leitura"] = leitura.valor
                    devices[leitura.id]["timestamp"] = leitura.timestamp

        else:
            print("[DEV_MNG] Mensagem recebida sem um tipo válido.")
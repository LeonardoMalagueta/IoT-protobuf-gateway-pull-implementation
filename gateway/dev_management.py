import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import time
import threading
import struct
import proto.projeto02_pb2 as proto

#O sensor que vai responder já sabe qual o grupo do multicast pois ele já ta escutando nele, mas a gente manda a porta unicast pra ele responder
#e isso ele nao sabe. assim ele nao precisa responder no multicast..

#================================== Scan da rede atras de devices ===============================
def send_discover_loop(grupo_multicast, porta_multicast, porta_unicast_udp):
    socket_udp_multi = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    socket_udp_multi.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

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
                    "estado": None,    # sensores não têm estado
                    "timestamp": time.time()
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
                    "estado": atuador.estado_inicial,
                    "timestamp": time.time()
                }
            print("[DEV_MNG] devices =", devices)
    #=========================================================================================================
    #==================================== MENSAGEM DO TIPO LEITURA ===========================================
        elif tipo_msg == "leitura":
            leitura = resposta.leitura

            print(f"[DEV_MNG] Leitura do sensor {leitura.id} recebida: valor={leitura.valor} timestamp={leitura.timestamp}")

            destinos = []

            with devices_lock:
                if leitura.id in devices:
                    # Atualiza info do sensor
                    devices[leitura.id]["ultima_leitura"] = leitura.valor
                    devices[leitura.id]["timestamp"] = leitura.timestamp

                    # Tipo do sensor (ex: "temperatura", "presenca")
                    tipo_sensor = devices[leitura.id]["tipo"]

                    # Se for sensor de temperatura → encaminha para ArCondicionado
                    if tipo_sensor == "temperatura":
                        destinos = [
                            (info["ip"], info["porta"])
                            for dev_id, info in devices.items()
                            if info["tipo"] == "ArCondicionado"
                        ]

                    # Se for sensor de presença → encaminha para Sirene
                    elif tipo_sensor == "presenca":
                        destinos = [
                            (info["ip"], info["porta"])
                            for dev_id, info in devices.items()
                            if info["tipo"] == "Sirene"
                        ]

            # Envia a mesma mensagem recebida do sensor para os atuadores destino
            for ip_dst, porta_dst in destinos:
                try:
                    socket_udp_uni.sendto(data, (ip_dst, porta_dst))
                    print(f"[DEV_MNG] Encaminhando leitura do sensor {leitura.id} para {ip_dst}:{porta_dst}")
                except Exception as e:
                    print(f"[DEV_MNG] Erro ao encaminhar leitura para {ip_dst}:{porta_dst} -> {e}")

        
        elif tipo_msg == "estado":
            status_atuador = resposta.estado
            print(f"[DEV_MNG] Status do Atuador {status_atuador.id}: {status_atuador.estado_atual}")
            
            with devices_lock:
                if status_atuador.id in devices:
                    devices[status_atuador.id]["estado"] = status_atuador.estado_atual
                    devices[status_atuador.id]["timestamp"] = status_atuador.timestamp

        else:
            print(f"[DEV_MNG] Mensagem recebida sem um tipo válido. {tipo_msg}")


def handle_client(conn, addr, devices, devices_lock):
    print(f"[DEV_MNG] Cliente conectado: {addr}")
    try:
        while True:
            raw_len = conn.recv(4)
            msg_len = int.from_bytes(raw_len, "big")
            data = conn.recv(msg_len)
            if not data: break
            
            req = proto.RequisicaoCliente()
            req.ParseFromString(data)
            
            tipo_req = req.WhichOneof("conteudo")

            if tipo_req == "comando":
                cmd_cliente = req.comando
                print(f"[DEV_MNG] Cliente enviando comando para {cmd_cliente.id_alvo}")
                
                alvo_ip = None
                alvo_porta = None
                
                with devices_lock:
                    if cmd_cliente.id_alvo in devices:
                        dev = devices[cmd_cliente.id_alvo]
                        alvo_ip = dev['ip']
                        alvo_porta = dev['porta']
                
                if alvo_ip and alvo_porta:
                    try:
                        sock_atuador = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock_atuador.connect((alvo_ip, alvo_porta))
                        resp_bytes = cmd_cliente.SerializeToString()
                        sock_atuador.sendall(len(resp_bytes).to_bytes(4, "big") + resp_bytes)
                        
                        raw_len = sock_atuador.recv(4)
                        msg_len = int.from_bytes(raw_len, "big")
                        resp_data = sock_atuador.recv(msg_len)
                        sock_atuador.close()
                        
                        conn.sendall((len(resp_data).to_bytes(4, "big") + resp_data))
                    except Exception as e:
                        print(f"[DEV_MNG] Erro ao falar com atuador: {e}")
                else:
                    print("[DEV_MNG] Atuador não encontrado ou offline.")
                    resp = proto.RespostaComando()
                    resp.id = cmd_cliente.id_alvo
                    resp.sucesso = False
                    resp.mensagem = "Atuador não encontrado"

                    resp_bytes = resp.SerializeToString()
                    conn.sendall(len(resp_bytes).to_bytes(4, "big") + resp_bytes)
            
            elif tipo_req == "pedir_lista":
                print("[DEV_MNG] Cliente solicitou lista de dispositivos.")
                
                lista_proto = proto.ListaDispositivos()
                
                with devices_lock:
                    for dev_id, info in devices.items():
                        d = lista_proto.dispositivos.add()
                        d.id = dev_id
                        d.tipo = info['tipo']
                        d.ip = info['ip']
                        d.porta = info['porta']
                        if 'ultima_leitura' in info and info['ultima_leitura'] is not None:
                            d.estado = f"{info['ultima_leitura']:.2f}"
                        else:
                            d.estado = str(info['estado'])
                        tempo_sem_aparecer_discovery = time.time() - info['timestamp']
                        if tempo_sem_aparecer_discovery < 15:
                            d.online = True
                        else:
                            d.online = False
                try:
                    data_bytes = lista_proto.SerializeToString()
                    conn.sendall((len(data_bytes).to_bytes(4, "big") + data_bytes))
                except:
                    print(f"Erro ao enviar os dados")
                    conn.close()
                    return
    except Exception as e:
        print(f"[DEV_MNG] Erro: {e}")
    finally:
        conn.close()

def tcp_server_clients(porta_tcp, devices, devices_lock):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", porta_tcp))
    sock.listen(5)
    print(f"[DEV_MNG] Aguardando Clientes TCP na porta {porta_tcp}...")
    
    while True:
        conn, addr = sock.accept()
        # Cria uma thread para cada cliente
        t = threading.Thread(target=handle_client, args=(conn, addr, devices, devices_lock))
        t.start()
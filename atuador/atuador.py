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
MEU_ID = "Atuador01"             #Identificador dele lá na lista
MEU_TIPO = "Lampada"    #tipo do dispositivo padroinzado
ESTADO_ATUAL = False #Informa o estado atual do atuador
MEU_PORTA = 5009            #porta unicast do dispositivo (diferente)

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

    print("[ATUADOR] esperando DISCOVERY...")

    while True:
        data, addr = sock.recvfrom(4096)    #recebe os dados e o endereço do sender diferente do recv(), com buffer de 4096bytes
        msg = proto.Descoberta()            #cria o protoobjeto

        try:
            msg.ParseFromString(data)       #desserializa
        except:
            continue

        if msg.inicia_descoberta == True:
            print("[ATUADOR] Recebi DISCOVERY:", msg)

            # salva a porta unicast do gateway
            gateway_addr = addr[0]
            gateway_port = msg.porta_resposta

            # monta resposta de anúncio
            resposta = proto.Resposta()
            atuador = resposta.atuador              # oneof tipo = atuador
            atuador.tipo = MEU_TIPO
            atuador.id = MEU_ID
            atuador.ip = "127.0.0.1"
            atuador.porta = MEU_PORTA
            atuador.estado_inicial = ESTADO_ATUAL

            # envia anúncio para o gateway via unicast
            sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
            print("[ATUADOR] respondi ao gateway.")

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

        leitura = proto.StatusAtuador()    # <-- usa exatamente o nome do .proto

        # dados da leitura
        leitura.id = MEU_ID
        leitura.estado_atual = ESTADO_ATUAL          # valor fake por enquanto
        leitura.timestamp = int(time.time())

        sock.sendto(leitura.SerializeToString(), (gateway_addr, gateway_port))
        print(f"[ATUADOR] enviando ESTADO → {gateway_addr}:{gateway_port}")

        time.sleep(5) # intervalo entre leituras

# ------------------------------------------------------------
# THREAD 3 — RECEBER COMANDOS VIA TCP
# ------------------------------------------------------------
def escutar_comandos_tcp():
    global ESTADO_ATUAL, MEU_PORTA

    # Configura o Socket TCP Server
    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.bind(("", MEU_PORTA))
    sock_tcp.listen(5) # Fila de espera


    while True:
        
        conn, addr = sock_tcp.accept()

        try:
            # Recebe os dados (1024 bytes deve ser suficiente para um comando simples)
            data = conn.recv(1024)
            if not data:
                conn.close()
                continue

            cmd = proto.Comando()
            cmd.ParseFromString(data)

            # Verifica se o comando é pra mim mesmo (segurança extra)
            if cmd.id_alvo == MEU_ID:
                print(f"[ATUADOR] Comando recebido: {cmd.tipo_comando}")
                
                # --- LOGICA DE ATUAÇÃO ---
                msg_retorno = "Estado inalterado"
                
                if cmd.tipo_comando == "LIGAR":
                    ESTADO_ATUAL = True
                    msg_retorno = "Atuador LIGADO com sucesso"
                
                elif cmd.tipo_comando == "DESLIGAR":
                    ESTADO_ATUAL = False
                    msg_retorno = "Atuador DESLIGADO com sucesso"
                
                resp = proto.RespostaComando()
                resp.id = MEU_ID
                resp.sucesso = True
                resp.mensagem = msg_retorno
                
                conn.send(resp.SerializeToString())
            else:
                print(f"[ATUADOR] Ignorando comando para ID errado: {cmd.id_alvo}")

        except Exception as e:
            print(f"[ATUADOR] Erro ao processar comando TCP: {e}")
        
        finally:
            conn.close()

# MAIN — INICIAR THREADS
t1 = threading.Thread(target=escutar_discovery, daemon=True)
t2 = threading.Thread(target=enviar_leituras, daemon=True)
t3 = threading.Thread(target=escutar_comandos_tcp, daemon=True)

t1.start()
t2.start()
t3.start()

while True:
    time.sleep(1)
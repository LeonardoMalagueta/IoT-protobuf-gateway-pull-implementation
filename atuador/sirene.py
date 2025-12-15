import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import struct
import threading
import time
import proto.projeto02_pb2 as proto

GRUPO = "224.1.1.1"
PORTA_GRUPO = 5007
MEU_ID = "SIR01"
MEU_TIPO = "Sirene"
MEU_PORTA = 5013           # mesma porta para UDP (leituras) e TCP (comandos)

gateway_addr = None
gateway_port = None

# Estado interno da sirene
ESTADO_ATUAL = False       # False = desligada, True = ligada
SISTEMA_ARMADO = False     # se True, presença ativa a sirene

lock_estado = threading.Lock()


# ------------------------------------------------------------
# FUNÇÃO AUXILIAR — ATUALIZA ESTADO A PARTIR DA PRESENÇA
# ------------------------------------------------------------
def tratar_leitura_presenca(valor):
    """
    valor > 0 significa presença detectada.
    Se o sistema estiver ARMADO, a sirene liga automaticamente.
    """
    global ESTADO_ATUAL, SISTEMA_ARMADO

    with lock_estado:
        if SISTEMA_ARMADO and valor > 0 and not ESTADO_ATUAL:
            ESTADO_ATUAL = True
            print("[SIR] PRESENÇA detectada e sistema ARMADO → LIGANDO SIRENE!")
        else:
            print(f"[SIR] Leitura de presença recebida: {valor} (armado={SISTEMA_ARMADO}, estado={ESTADO_ATUAL})")


# ------------------------------------------------------------
# THREAD 1 — ESCUTAR DISCOVERY (MULTICAST) E ANUNCIAR SIRENE
# ------------------------------------------------------------
def escutar_discovery():
    global gateway_addr, gateway_port

    # Descobrir IP local
    sock_ip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock_ip.connect(('10.255.255.255', 1))
        IP = sock_ip.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        sock_ip.close()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORTA_GRUPO))

    mreq = struct.pack("4sl", socket.inet_aton(GRUPO), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print("[SIR] Aguardando DISCOVERY do gateway...")

    while True:
        data, addr = sock.recvfrom(4096)
        msg = proto.Descoberta()
        try:
            msg.ParseFromString(data)
        except:
            continue

        if msg.inicia_descoberta:
            print("[SIR] DISCOVERY recebido do gateway:", addr)
            gateway_addr = addr[0]
            gateway_port = msg.porta_resposta

            resposta = proto.Resposta()
            atuador = resposta.atuador
            atuador.tipo = MEU_TIPO
            atuador.id = MEU_ID
            atuador.ip = IP
            atuador.porta = MEU_PORTA
            atuador.estado_inicial = ESTADO_ATUAL

            sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
            print("[SIR] Anúncio de SIRENE enviado ao gateway.")


# ------------------------------------------------------------
# THREAD 2 — ENVIAR ESTADO PERIÓDICO PARA O GATEWAY (UDP)
# ------------------------------------------------------------
def enviar_estado():
    global gateway_addr, gateway_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        if gateway_addr is None:
            time.sleep(1)
            continue

        resposta = proto.Resposta()
        estado = resposta.estado

        with lock_estado:
            estado.id = MEU_ID
            estado.estado_atual = ESTADO_ATUAL
            estado.timestamp = int(time.time())

        sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
        print(f"[SIR] Enviando ESTADO para {gateway_addr}:{gateway_port} (estado={ESTADO_ATUAL})")

        time.sleep(5)


# ------------------------------------------------------------
# THREAD 3 — RECEBER LEITURAS DO SENSOR DE PRESENÇA (UDP)
# ------------------------------------------------------------
def escutar_leituras_sensor():
    """
    Escuta mensagens Resposta.leitura encaminhadas pelo gateway, vindas do sensor de presença.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", MEU_PORTA))

    print(f"[SIR] Aguardando leituras de presença no UDP {MEU_PORTA}...")

    while True:
        data, addr = sock.recvfrom(4096)
        resp = proto.Resposta()
        try:
            resp.ParseFromString(data)
        except Exception as e:
            print("[SIR] Mensagem UDP inválida recebida:", e)
            continue

        tipo = resp.WhichOneof("tipo")
        if tipo == "leitura":
            leitura = resp.leitura
            print(f"[SIR] Leitura recebida do sensor {leitura.id}: valor={leitura.valor}")
            tratar_leitura_presenca(leitura.valor)


# ------------------------------------------------------------
# THREAD 4 — RECEBER COMANDOS TCP DO CLIENTE (VIA GATEWAY)
# ------------------------------------------------------------
def escutar_comandos_tcp():
    global ESTADO_ATUAL, SISTEMA_ARMADO

    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.bind(("", MEU_PORTA))
    sock_tcp.listen(5)

    print(f"[SIR] Servidor TCP da sirene escutando na porta {MEU_PORTA}...")

    while True:
        conn, addr = sock_tcp.accept()
        try:
            raw_len = conn.recv(4)
            if not raw_len:
                conn.close()
                continue

            msg_len = int.from_bytes(raw_len, "big")
            data = conn.recv(msg_len)
            if not data:
                conn.close()
                continue

            cmd = proto.Comando()
            cmd.ParseFromString(data)

            if cmd.id_alvo == MEU_ID:
                print(f"[SIR] Comando recebido: {cmd.tipo_comando}")

                msg_retorno = "Estado inalterado"

                with lock_estado:
                    if cmd.tipo_comando == "LIGAR":
                        ESTADO_ATUAL = True
                        msg_retorno = "Sirene LIGADA manualmente"

                    elif cmd.tipo_comando == "DESLIGAR":
                        ESTADO_ATUAL = False
                        msg_retorno = "Sirene DESLIGADA manualmente"

                    elif cmd.tipo_comando == "ARMAR":
                        SISTEMA_ARMADO = True
                        msg_retorno = "Sistema de alarme ARMADO"

                    elif cmd.tipo_comando == "DESARMAR":
                        SISTEMA_ARMADO = False
                        ESTADO_ATUAL = False
                        msg_retorno = "Sistema de alarme DESARMADO e sirene DESLIGADA"

                resp = proto.RespostaComando()
                resp.id = MEU_ID
                resp.sucesso = True
                resp.mensagem = msg_retorno

                resp_bytes = resp.SerializeToString()
                conn.sendall(len(resp_bytes).to_bytes(4, "big") + resp_bytes)
            else:
                print(f"[SIR] Comando para outro dispositivo ignorado: {cmd.id_alvo}")

        except Exception as e:
            print(f"[SIR] Erro ao processar comando TCP: {e}")
        finally:
            conn.close()


# ------------------------------------------------------------
# MAIN — INICIAR THREADS
# ------------------------------------------------------------
if __name__ == "__main__":
    t1 = threading.Thread(target=escutar_discovery, daemon=True)
    t2 = threading.Thread(target=enviar_estado, daemon=True)
    t3 = threading.Thread(target=escutar_leituras_sensor, daemon=True)
    t4 = threading.Thread(target=escutar_comandos_tcp, daemon=True)

    t1.start()
    t2.start()
    t3.start()
    t4.start()

    while True:
        time.sleep(1)
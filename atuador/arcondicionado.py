import sys
import os

# Ajuste do caminho para conseguir importar o módulo protobuf
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import struct
import threading
import time
import proto.projeto02_pb2 as proto

# Configuração básica de rede
GRUPO = "224.1.1.1"
PORTA_GRUPO = 5007
MEU_ID = "AC01"
MEU_TIPO = "ArCondicionado"
MEU_PORTA = 5010            # porta TCP e UDP (mesmo número, protocolos diferentes)

# Endereço do gateway descoberto via multicast
gateway_addr = None
gateway_port = None

# Estado interno do ar-condicionado
ESTADO_ATUAL = False        # False = desligado, True = ligado
ULTIMA_TEMP = None          # última temperatura recebida
SETPOINT = 23.0             # temperatura alvo em °C
HISTERESIS = 1.0            # faixa de histerese para evitar liga/desliga toda hora

# Se True, o ar-condicionado pode ligar/desligar automaticamente pela temperatura
CONTROLE_AUTOMATICO = True

lock_estado = threading.Lock()


# ------------------------------------------------------------
# FUNÇÃO AUXILIAR — ATUALIZAR ESTADO EM FUNÇÃO DA TEMPERATURA
# ------------------------------------------------------------
def atualizar_estado_por_temperatura(temp):
    """Atualiza o estado do ar-condicionado com base na temperatura medida."""
    global ESTADO_ATUAL, ULTIMA_TEMP, CONTROLE_AUTOMATICO
    ULTIMA_TEMP = temp

    with lock_estado:
        # Se o controle automático estiver desativado, não mexe no estado
        if not CONTROLE_AUTOMATICO:
            print(f"[AC] Leitura {temp}°C recebida, mas controle automático está DESATIVADO. Ignorando.")
            return

        # Se a temperatura estiver muito alta → ligar
        if temp > SETPOINT + HISTERESIS and not ESTADO_ATUAL:
            ESTADO_ATUAL = True
            print(f"[AC] Temperatura {temp}°C > {SETPOINT + HISTERESIS}°C → LIGAR ar-condicionado (modo automático)")
        # Se a temperatura estiver suficientemente baixa → desligar
        elif temp < SETPOINT - HISTERESIS and ESTADO_ATUAL:
            ESTADO_ATUAL = False
            print(f"[AC] Temperatura {temp}°C < {SETPOINT - HISTERESIS}°C → DESLIGAR ar-condicionado (modo automático)")



# ------------------------------------------------------------
# THREAD 1 — ESCUTAR MENSAGENS DE DISCOVERY (MULTICAST)
# ------------------------------------------------------------
def escutar_discovery():
    """Escuta o grupo multicast e responde às mensagens de descoberta do gateway."""
    global gateway_addr, gateway_port

    # Descobrir IP local
    socket_ip_atuador = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        socket_ip_atuador.connect(('10.255.255.255', 1))
        IP = socket_ip_atuador.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        socket_ip_atuador.close()

    # Socket para ouvir o grupo multicast
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", PORTA_GRUPO))

    # Entrar no grupo multicast
    mreq = struct.pack("4sl", socket.inet_aton(GRUPO), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print("[AC] Aguardando DISCOVERY no grupo multicast...")

    while True:
        data, addr = sock.recvfrom(4096)
        msg = proto.Descoberta()

        try:
            msg.ParseFromString(data)
        except:
            continue

        if msg.inicia_descoberta:
            print("[AC] DISCOVERY recebido:", msg)

            gateway_addr = addr[0]
            gateway_port = msg.porta_resposta

            # Monta a resposta de anúncio do ATUADOR
            resposta = proto.Resposta()
            atuador = resposta.atuador
            atuador.tipo = MEU_TIPO
            atuador.id = MEU_ID
            atuador.ip = IP
            atuador.porta = MEU_PORTA
            atuador.estado_inicial = ESTADO_ATUAL

            sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
            print("[AC] Anúncio de ArCondicionado enviado ao gateway.")


# ------------------------------------------------------------
# THREAD 2 — ENVIAR ESTADO PERIÓDICO PARA O GATEWAY (UDP)
# ------------------------------------------------------------
def enviar_estado():
    """Envia periodicamente o estado atual do ar-condicionado para o gateway via UDP."""
    global gateway_addr, gateway_port

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        if gateway_addr is None:
            # Ainda não sabemos o endereço do gateway (ninguém mandou DISCOVERY)
            time.sleep(1)
            continue

        resposta = proto.Resposta()
        estado = resposta.estado

        with lock_estado:
            estado.id = MEU_ID
            estado.estado_atual = ESTADO_ATUAL
            estado.timestamp = int(time.time())

        sock.sendto(resposta.SerializeToString(), (gateway_addr, gateway_port))
        print(f"[AC] Enviando ESTADO para {gateway_addr}:{gateway_port} (estado={ESTADO_ATUAL})")

        time.sleep(5)  # período de envio de estado (pode ajustar se quiser)


# ------------------------------------------------------------
# THREAD 3 — RECEBER LEITURAS DO SENSOR (UDP UNICAST)
# ------------------------------------------------------------
def escutar_leituras_sensor():
    """
    Escuta, via UDP, mensagens do tipo Resposta.leitura que o gateway encaminha
    com as leituras de temperatura dos sensores.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", MEU_PORTA))   # mesma porta usada para TCP, mas aqui é UDP

    print(f"[AC] Aguardando LEITURAS de temperatura no UDP {MEU_PORTA}...")

    while True:
        data, addr = sock.recvfrom(4096)
        resp = proto.Resposta()
        try:
            resp.ParseFromString(data)
        except Exception as e:
            print("[AC] Mensagem UDP inválida recebida:", e)
            continue

        tipo = resp.WhichOneof("tipo")
        if tipo == "leitura":
            leitura = resp.leitura
            print(f"[AC] Leitura recebida do sensor {leitura.id}: {leitura.valor}°C")
            atualizar_estado_por_temperatura(leitura.valor)


# ------------------------------------------------------------
# THREAD 4 — RECEBER COMANDOS VIA TCP (DO CLIENTE, VIA GATEWAY)
# ------------------------------------------------------------
def escutar_comandos_tcp():
    """
    Abre um servidor TCP para receber comandos encaminhados pelo gateway.
    Possíveis comandos:
      - LIGAR
      - DESLIGAR
      - SETPOINT (usa o campo parametro do Comando para o valor em °C)
    """
    global ESTADO_ATUAL, SETPOINT, CONTROLE_AUTOMATICO

    sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_tcp.bind(("", MEU_PORTA))
    sock_tcp.listen(5)

    print(f"[AC] Servidor TCP escutando na porta {MEU_PORTA}...")

    while True:
        conn, addr = sock_tcp.accept()
        try:
            # Protocolo: primeiro 4 bytes com o tamanho da mensagem
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
                print(f"[AC] Comando recebido: {cmd.tipo_comando} param={cmd.parametro}")

                msg_retorno = "Estado inalterado"

                with lock_estado:
                    if cmd.tipo_comando == "LIGAR":
                        ESTADO_ATUAL = True
                        # Ao ligar pelo cliente, voltamos a permitir controle automático
                        CONTROLE_AUTOMATICO = True
                        msg_retorno = "Ar-condicionado LIGADO e controle automático ATIVADO"

                    elif cmd.tipo_comando == "DESLIGAR":
                        ESTADO_ATUAL = False
                        # Ao desligar pelo cliente, travamos o controle automático
                        CONTROLE_AUTOMATICO = False
                        msg_retorno = "Ar-condicionado DESLIGADO e controle automático DESATIVADO"

                    elif cmd.tipo_comando == "SETPOINT":
                        SETPOINT = cmd.parametro
                        msg_retorno = f"Setpoint ajustado para {SETPOINT:.1f} °C"


                # Monta a resposta para o cliente
                resp = proto.RespostaComando()
                resp.id = MEU_ID
                resp.sucesso = True
                resp.mensagem = msg_retorno

                resp_bytes = resp.SerializeToString()
                conn.sendall(len(resp_bytes).to_bytes(4, "big") + resp_bytes)
            else:
                print(f"[AC] Comando para outro ID ignorado: {cmd.id_alvo}")

        except Exception as e:
            print(f"[AC] Erro ao processar comando TCP: {e}")
        finally:
            conn.close()


# ------------------------------------------------------------
# MAIN — INICIALIZAÇÃO DAS THREADS
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

    # Loop principal só pra manter o programa vivo
    while True:
        time.sleep(1)

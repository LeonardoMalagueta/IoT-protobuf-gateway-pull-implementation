import sys
import os

# Permite importar o módulo protobuf gerado
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import struct
import time
import proto.projeto02_pb2 as proto

GRUPO = "224.1.1.1"         # IP do grupo multicast definido
PORTA_GRUPO = 5007          # Porta do grupo multicast (igual à dos dispositivos)
PORTA_TCP_GATEWAY = 7000    # Porta TCP onde o gateway atende clientes

gateway_addr = None         # IP do gateway (descoberto no discovery)


# =====================================================================
# FUNÇÃO DE CORES (APENAS PRA ORGANIZAR SAÍDA NO TERMINAL)
# =====================================================================
def color(cor, msg):
    """Muda cor da mensagem no terminal usando códigos ANSI."""
    if cor == "green":
        return f"\033[32m{msg}\033[0m"
    elif cor == "red":
        return f"\033[31m{msg}\033[0m"
    elif cor == "yellow":
        return f"\033[33m{msg}\033[0m"
    return msg


# =====================================================================
# DESCOBRIR GATEWAY VIA MULTICAST
# =====================================================================
def encontrar_gateway():
    """
    Escuta o grupo multicast e espera receber uma mensagem Descoberta
    enviada pelo gateway. Usa o IP de origem dessa mensagem como IP do gateway.
    """
    print(color("yellow", "[CLIENTE] Procurando GATEWAY..."))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind(('', PORTA_GRUPO))
    except:
        print(color("red", f"[ERRO] Não foi possível abrir a porta {PORTA_GRUPO}."))
        return None

    mreq = struct.pack("4sl", socket.inet_aton(GRUPO), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = proto.Descoberta()
            msg.ParseFromString(data)

            if msg.inicia_descoberta:
                sock.close()
                print(color("green", f"[CLIENTE] Gateway encontrado em: {addr[0]}"))
                return addr[0]

        except Exception:
            continue


# =====================================================================
# CONEXÃO TCP COM O GATEWAY
# =====================================================================
def conectar_gateway(ip):
    """
    Tenta conectar ao gateway via TCP na porta PORTA_TCP_GATEWAY.
    Repite até conseguir.
    """
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, PORTA_TCP_GATEWAY))
            print(color("green", "[CLIENTE] Conectado ao gateway!"))
            return sock
        except Exception:
            print(color("red", "[CLIENTE] Falha ao conectar. Tentando novamente em 2s..."))
            time.sleep(2)


# =====================================================================
# LISTAR DISPOSITIVOS (PEDIR LISTA AO GATEWAY)
# =====================================================================
def listar_dispositivos(sock):
    """
    Envia uma RequisicaoCliente com 'pedir_lista = True' (com prefixo de tamanho)
    e recebe de volta uma ListaDispositivos (também com prefixo de tamanho).
    """
    req = proto.RequisicaoCliente()
    req.pedir_lista = True

    data = req.SerializeToString()
    # ENVIO: 4 bytes de tamanho + mensagem serializada
    sock.sendall(len(data).to_bytes(4, "big") + data)

    # RESPOSTA: primeiro 4 bytes de tamanho
    raw_len = sock.recv(4)
    if not raw_len:
        raise RuntimeError("Conexão fechada ao tentar ler tamanho da lista.")
    msg_len = int.from_bytes(raw_len, "big")

    resposta = sock.recv(msg_len)
    if not resposta:
        raise RuntimeError("Conexão fechada ao tentar ler a lista de dispositivos.")

    lista = proto.ListaDispositivos()
    lista.ParseFromString(resposta)
    return lista


# =====================================================================
# ENVIAR COMANDO PARA UM ATUADOR (LIGAR/DESLIGAR/SETPOINT)
# =====================================================================
def enviar_comando(sock, alvo, cmd_str, parametro=0.0):
    """
    Monta uma RequisicaoCliente com um Comando e envia ao gateway.
    O gateway encaminha para o atuador e devolve uma RespostaComando.
    Usa o MESMO protocolo de tamanho que o código original (4 bytes).
    """
    req = proto.RequisicaoCliente()
    cmd = req.comando
    cmd.id_alvo = alvo
    cmd.tipo_comando = cmd_str
    cmd.parametro = parametro  # para LIGAR/DESLIGAR será ignorado; para SETPOINT é o valor em °C

    data = req.SerializeToString()
    sock.sendall(len(data).to_bytes(4, "big") + data)

    # Lê tamanho da resposta
    raw_len = sock.recv(4)
    if not raw_len:
        raise RuntimeError("Conexão fechada ao tentar ler tamanho da resposta de comando.")
    msg_len = int.from_bytes(raw_len, "big")

    resposta = sock.recv(msg_len)
    if not resposta:
        raise RuntimeError("Conexão fechada ao tentar ler a resposta de comando.")

    resp = proto.RespostaComando()
    resp.ParseFromString(resposta)
    return resp


# =====================================================================
# LOOP DE MENU INTERATIVO
# =====================================================================
def loop_menu(sock):
    """
    Mostra o menu, lê comandos do usuário e fala com o gateway.
    Retorna:
        - False se o usuário escolheu sair.
        - True se houve erro de conexão e precisamos tentar reconectar.
    """
    while True:
        print("\n--- MENU ---")
        print("1. Listar Dispositivos")
        print("2. Enviar Comando (LIGAR/DESLIGAR)")
        print("3. Ajustar SETPOINT de ArCondicionado")
        print("0. Sair")
        comando = input("Opção: ")

        try:
            # SAIR
            if comando == "0":
                sock.close()
                return False

            # LISTAR DISPOSITIVOS
            elif comando == "1":
                lista = listar_dispositivos(sock)
                print("\n--- DISPOSITIVOS CONECTADOS ---")
                if not lista.dispositivos:
                    print(color("yellow", "Nenhum dispositivo cadastrado ainda."))
                for dev in lista.dispositivos:
                    conexao = color("green", "ONLINE") if dev.online else color("red", "OFFLINE")
                    print(f"ID: {dev.id} | Tipo: {dev.tipo} | Estado: {dev.estado} | "
                          f"IP: {dev.ip}:{dev.porta} | {conexao}")

            # COMANDO LIGAR/DESLIGAR
            elif comando == "2":
                alvo = input("ID do Atuador (ex: Atuador01, AC01, SIR01): ").strip()
                cmd_str = input("Comando (LIGAR/DESLIGAR/ARMAR/DESARMAR): ").strip().upper()

                if cmd_str not in ("LIGAR", "DESLIGAR", "ARMAR", "DESARMAR"):
                    print(color("red", "Comando inválido. Use LIGAR, DESLIGAR, ARMAR ou DESARMAR."))
                    continue

                resp = enviar_comando(sock, alvo, cmd_str)
                print(f"[CLIENTE] Resposta: {resp.mensagem} (Sucesso: {resp.sucesso})")

            # AJUSTAR SETPOINT DO AR-CONDICIONADO
            elif comando == "3":
                alvo = input("ID do ArCondicionado (ex: AC01): ").strip()
                setpoint_str = input("Novo setpoint em °C (ex: 23.5): ").replace(",", ".").strip()

                try:
                    setpoint = float(setpoint_str)
                except ValueError:
                    print(color("red", "Valor de setpoint inválido. Digite um número, ex: 23.5"))
                    continue

                resp = enviar_comando(sock, alvo, "SETPOINT", parametro=setpoint)
                print(f"[CLIENTE] Resposta: {resp.mensagem} (Sucesso: {resp.sucesso})")

            else:
                print(color("red", "Opção inválida. Tente novamente."))

        except (BrokenPipeError, ConnectionResetError):
            print(color("red", "[CLIENTE] Conexão perdida com o gateway!"))
            return True  # sinaliza reconectar
        except RuntimeError as e:
            print(color("red", f"[CLIENTE] Erro: {e}"))
            return True  # também pede reconexão


# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    gateway_addr = encontrar_gateway()
    if gateway_addr is None:
        print(color("red", "[CLIENTE] Não foi possível encontrar o gateway. Encerrando."))
        sys.exit(1)

    sock = conectar_gateway(gateway_addr)

    while True:
        precisa_reconectar = loop_menu(sock)

        if not precisa_reconectar:
            print(color("yellow", "[CLIENTE] Encerrando cliente."))
            break

        # Reconectar automaticamente
        print(color("yellow", "[CLIENTE] Tentando reconectar..."))
        sock = conectar_gateway(gateway_addr)

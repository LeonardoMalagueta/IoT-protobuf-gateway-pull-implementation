import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import socket
import struct
import time
import proto.projeto02_pb2 as proto

GRUPO = "224.1.1.1"         #ip do grupo multicast definido
PORTA_GRUPO = 5007          #porta do grupo multicast (igual)
PORTA_TCP_GATEWAY = 7000

gateway_addr = None         # IP do gateway (descoberto no discovery)


def color(cor, msg): 
    """Muda cor de msg"""
    if cor == "green":
        return f"\033[32m{msg}\033[0m"
    elif cor == "red":
        return f"\033[31m{msg}\033[0m"
    elif cor == "yellow":
        return f"\033[33m{msg}\033[0m"
    return msg


def encontrar_gateway():
    print(color("yellow", "[Cliente] Procurando GATEWAY..."))

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


def conectar_gateway(ip):
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, PORTA_TCP_GATEWAY))
            print(color("green", "[CLIENTE] Conectado ao gateway!"))
            return sock
        except Exception:
            print(color("red", "[CLIENTE] Falha ao conectar. Tentando novamente em 2s..."))
            time.sleep(2)


def listar_dispositivos(sock):
    req = proto.RequisicaoCliente()
    req.pedir_lista = True

    data = req.SerializeToString()
    sock.sendall(len(data).to_bytes(4, "big") + data)

    raw_len = sock.recv(4)
    msg_len = int.from_bytes(raw_len, "big")
    resposta = sock.recv(msg_len)

    lista = proto.ListaDispositivos()
    lista.ParseFromString(resposta)
    return lista

def enviar_comando(sock, alvo, cmd_str):
    req = proto.RequisicaoCliente()
    cmd = req.comando
    cmd.id_alvo = alvo
    cmd.tipo_comando = cmd_str

    data = req.SerializeToString()
    sock.sendall(len(data).to_bytes(4, "big") + data)

    raw_len = sock.recv(4)
    msg_len = int.from_bytes(raw_len, "big")
    resposta = sock.recv(msg_len)

    resp = proto.RespostaComando()
    resp.ParseFromString(resposta)
    return resp
    
def loop_menu(sock):
    while True:
        print("\n--- MENU ---")
        print("1. Listar Dispositivos")
        print("2. Enviar Comando (LIGAR/DESLIGAR)")
        print("0. Sair")
        comando = input("Opção: ")

        try:
            if comando == "0":
                sock.close()
                return False

            elif comando == "1":
                lista = listar_dispositivos(sock)
                print("\n--- DISPOSITIVOS CONECTADOS ---")
                for dev in lista.dispositivos:
                    conexao = color("green", "ONLINE") if dev.online else color("red", "OFFLINE")
                    print(f"ID: {dev.id} | Tipo: {dev.tipo} | Estado: {dev.estado} | "
                          f"IP: {dev.ip}:{dev.porta} | {conexao}")

            elif comando == "2":
                alvo = input("ID do Atuador (ex: Atuador01): ")
                cmd_str = input("Comando (LIGAR/DESLIGAR): ").upper()
                resp = enviar_comando(sock, alvo, cmd_str)
                print(f"[CLIENTE] Resposta: {resp.mensagem} (Sucesso: {resp.sucesso})")

        except (BrokenPipeError, ConnectionResetError):
            print(color("red", "[CLIENTE] Conexão perdida com o gateway!"))
            return True  # sinaliza reconectar


if __name__ == "__main__":
    gateway_addr = encontrar_gateway()

    sock = conectar_gateway(gateway_addr)

    while True:
        precisa_reconectar = loop_menu(sock)

        if not precisa_reconectar:
            print(color("yellow", "[CLIENTE] Encerrando cliente."))
            break

        # reconectar automaticamente
        print(color("yellow", "[CLIENTE] Tentando reconectar..."))
        sock = conectar_gateway(gateway_addr)

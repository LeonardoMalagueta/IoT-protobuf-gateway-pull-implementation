# multicast_listener.py
import socket
from proto import smartcity_pb2
from device_manager import update_device

MCAST_GRP = "224.1.1.1"
MCAST_PORT = 5007

def start_multicast_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #socket UDP
    sock.bind(('', MCAST_PORT))                             #porta multicast definida

    mreq = socket.inet_aton(MCAST_GRP) + socket.inet_aton("0.0.0.0")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)  #join no grupo multicast 244.1.1.1 o que permite escutar nesse endereço

    print(f"[Gateway] Escutando multicast em {MCAST_GRP}:{MCAST_PORT}")

    while True:                                                         #Loop de escuta infinita rodando na thread
        data, addr = sock.recvfrom(4096)                                #espera o pacote chegar e recebe 
        try:                                                            #caso seja um pacote de dados do tipo anuncio de dispositivo
            msg = smartcity_pb2.DeviceAnnounce()
            msg.ParseFromString(data)
        except:                                                         #se nao for reseta o loop
            continue    

        update_device(msg)                                              #se for faz um update_devices com o payload da mensagem
        #print(f"[ANNOUNCE] {msg.device_id} ({msg.device_type}) IP={msg.ip}") //DEBUG DE ESCUTA DOS DISPOSITIVOS

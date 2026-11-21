import ctypes
import fcntl
from socket import AF_NETLINK, SOCK_DGRAM, socket

from modules import log

logger = log.get("promisc")

IFF_PROMISC = 0x100
SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914


class ifreq(ctypes.Structure):
    _fields_ = [("ifr_ifrn", ctypes.c_char * 16), ("ifr_flags", ctypes.c_short)]


def set(nic, state):
    logger.info("promiscuous mode", nic=nic, enabled=bool(state))
    ifr = ifreq()
    ifr.ifr_ifrn = str.encode(nic)
    with socket(AF_NETLINK, SOCK_DGRAM) as s:
        fcntl.ioctl(s.fileno(), SIOCGIFFLAGS, ifr)  # G for Get
        if state:
            ifr.ifr_flags |= IFF_PROMISC
        else:
            ifr.ifr_flags &= ~IFF_PROMISC
        fcntl.ioctl(s.fileno(), SIOCSIFFLAGS, ifr)  # S for Set

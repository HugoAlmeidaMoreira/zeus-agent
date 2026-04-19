import socket
import sys

domain = "default._domainkey.hugomoreira.eu"
try:
    answers = socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP, socket.AI_CANONNAME)
    print(f"Resolving {domain}: {answers}")
except Exception as e:
    print(f"Error resolving {domain}: {e}")

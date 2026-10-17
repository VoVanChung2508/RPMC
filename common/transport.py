from __future__ import annotations

import ipaddress
import os
import socket
import ssl

_PRIVATE_IPV4_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def require_lan_host(host: str) -> None:
    if is_loopback(host):
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("LAN connections must use a specific private IPv4 address") from None
    if address.version != 4 or not any(address in network for network in _PRIVATE_IPV4_NETWORKS):
        raise ValueError("LAN connections must use a specific private IPv4 address")


def create_server_context(
    host: str,
    certfile: str | None = None,
    keyfile: str | None = None,
) -> ssl.SSLContext | None:
    certfile = certfile or os.environ.get("RPMC_TLS_CERTFILE")
    keyfile = keyfile or os.environ.get("RPMC_TLS_KEYFILE")
    if bool(certfile) != bool(keyfile):
        raise ValueError("Set both RPMC_TLS_CERTFILE and RPMC_TLS_KEYFILE for TLS")
    if not is_loopback(host):
        require_lan_host(host)
        if not certfile or not keyfile:
            raise ValueError("Non-loopback binding requires TLS certificate and private key files")
    if not certfile:
        return None

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile, keyfile)
    return context


def create_client_context(host: str, cafile: str | None = None) -> ssl.SSLContext | None:
    cafile = cafile or os.environ.get("RPMC_TLS_CA_FILE")
    if not is_loopback(host):
        require_lan_host(host)
    if not cafile:
        if is_loopback(host):
            return None
        raise ValueError("Non-loopback connections require RPMC_TLS_CA_FILE with a trusted CA certificate")

    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cafile)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def wrap_client_socket(
    sock: socket.socket,
    host: str,
    context: ssl.SSLContext | None,
) -> socket.socket:
    if context is None:
        return sock
    return context.wrap_socket(sock, server_hostname=host)

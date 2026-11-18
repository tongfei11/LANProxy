"""Supervise redsocks and relay local DNS over HTTPS through it."""
import http.client
import socket
import socketserver
import signal
import ssl
import struct
import subprocess
import sys
import threading
import time
from contextlib import ExitStack

from core import DNS_MARK, DNS_PORT, REDSOCKS, TCP_PORT
TIMEOUT = 5
RESOLVER = 'cloudflare-dns.com'
CONTEXT = ssl.create_default_context()
SLOTS = threading.BoundedSemaphore(16)


def doh_query(query):
    if len(query) < 12:
        raise ValueError('short DNS query')
    # The output redirect sends this IPv4 connection through redsocks.
    with socket.create_connection(('1.1.1.1', 443), timeout=TIMEOUT) as stream:
        with CONTEXT.wrap_socket(stream, server_hostname=RESOLVER) as tls:
            request = http.client.HTTPConnection(RESOLVER, timeout=TIMEOUT)
            request.sock = tls
            request.request('POST', '/dns-query', body=query, headers={
                'Content-Type': 'application/dns-message',
                'Accept': 'application/dns-message',
                'Connection': 'close',
            })
            with request.getresponse() as response:
                answer = response.read(65536) if response.status == 200 else b''
            if not 12 <= len(answer) <= 65535 or answer[:2] != query[:2]:
                raise ValueError('invalid DNS response')
            return answer


def tcp_query(query):
    # Skip only the port-53 capture. The normal TCP output rule still sends
    # this connection through redsocks to the resolver.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.settimeout(TIMEOUT)
        stream.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, DNS_MARK)
        stream.connect(('1.1.1.1', 53))
        stream.sendall(struct.pack('!H', len(query)) + query)
        with stream.makefile('rb') as reply:
            header = reply.read(2)
            if len(header) != 2:
                raise ValueError('missing DNS response length')
            size, = struct.unpack('!H', header)
            answer = reply.read(size)
            if len(answer) != size or size < 12 or answer[:2] != query[:2]:
                raise ValueError('invalid DNS response')
            return answer


def answer_query(query):
    if len(query) < 12:
        return b''
    for resolve in (doh_query, tcp_query):
        try:
            return resolve(query)
        except (OSError, ValueError, http.client.HTTPException):
            continue
    # Preserve the ID and signal SERVFAIL to the resolver.
    return query[:2] + bytes((0x80 | (query[2] & 1), 0x82)) + bytes(8)


class BoundedServer(socketserver.ThreadingMixIn):
    daemon_threads = True
    allow_reuse_address = True

    def process_request(self, request, address):
        if not SLOTS.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            SLOTS.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            SLOTS.release()


class DNSDatagram(socketserver.BaseRequestHandler):
    def handle(self):
        query, sock = self.request
        answer = answer_query(query)
        if answer:
            sock.sendto(answer, self.client_address)


class DNSStream(socketserver.StreamRequestHandler):
    timeout = TIMEOUT

    def handle(self):
        try:
            header = self.rfile.read(2)
            if len(header) != 2:
                return
            size, = struct.unpack('!H', header)
            query = self.rfile.read(size)
            if len(query) == size:
                answer = answer_query(query)
                if answer:
                    self.wfile.write(struct.pack('!H', len(answer)) + answer)
        except OSError:
            pass


class UDPServer(BoundedServer, socketserver.UDPServer):
    max_packet_size = 65535


class TCPServer(BoundedServer, socketserver.TCPServer):
    pass


class UDP6Server(UDPServer):
    address_family = socket.AF_INET6


class TCP6Server(TCPServer):
    address_family = socket.AF_INET6


def main(config):
    with ExitStack() as stack:
        servers = [stack.enter_context(cls((host, DNS_PORT), handler)) for cls, host, handler in (
            (UDPServer, '127.0.0.1', DNSDatagram), (TCPServer, '127.0.0.1', DNSStream),
            (UDP6Server, '::1', DNSDatagram), (TCP6Server, '::1', DNSStream),
        )]
        with subprocess.Popen([REDSOCKS, '-c', config]) as proxy:
            try:
                for server in servers:
                    threading.Thread(target=server.serve_forever, daemon=True).start()
                deadline = time.monotonic() + TIMEOUT
                while proxy.poll() is None and time.monotonic() < deadline:
                    try:
                        with socket.create_connection(('127.0.0.1', TCP_PORT), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    return 1
                print('READY', flush=True)
                return proxy.wait() or 1
            finally:
                if proxy.poll() is None:
                    proxy.terminate()


if __name__ == '__main__':
    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    sys.exit(main(sys.argv[1]))

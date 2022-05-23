import socket
import ssl
import select
import threading
import os
import argparse
import logging

from urllib.parse import urlparse
from typing import List, Tuple, Union, Optional

__author__ = 'Glemison C. Dutra'
__version__ = '1.0.1'

usage = f'''
    HTTP Proxy v{__version__} - {__author__}

    # Uso:
        HTTPS: 
            python3 proxy.py --https --cert cert.pem --port 443
        
        HTTP:
            python3 proxy.py --http --port 80
    
    # Uso em background:
        HTTPS:
            screen -dmS proxy python3 proxy.py --https --cert cert.pem --port 443
        
        HTTP:
            screen -dmS proxy python3 proxy.py --http --port 80
        
    # Finalizar uso em background:
        screen -X -S proxy quit
'''

logger = logging.getLogger(__name__)

DEFAULT_RESPONSE = b'HTTP/1.1 101 Connection Established\r\n\r\n'
REMOTE_ADDRESS = ('0.0.0.0', 22)


class HttpParser:
    def __init__(self) -> None:
        self.method = None
        self.body = None
        self.url = None
        self.headers = {}

    def parse(self, data: bytes) -> None:
        data = data.decode('utf-8')
        lines = data.split('\r\n')

        self.method, self.url, self.version = lines[0].split()
        self.url = urlparse(self.url)

        self.headers.update(
            {k: v.strip() for k, v in [line.split(':', 1) for line in lines[1:] if ':' in line]}
        )

        self.body = (
            '\r\n'.join(lines[-1:])
            if not self.headers.get('Content-Length')
            else '\r\n'.join(lines[-1 : -1 * int(self.headers['Content-Length'])])
        )

    def build(self) -> bytes:
        base = f'{self.method} {self.url.path} {self.version}\r\n'
        headers = '\r\n'.join(f'{k}: {v}' for k, v in self.headers.items()) + '\r\n' * 2
        return base.encode('utf-8') + headers.encode('utf-8') + self.body.encode('utf-8')


class Connection:
    def __init__(self, conn: Union[socket.socket, ssl.SSLSocket], addr: Tuple[str, int]):
        self.__conn = conn
        self.__addr = addr
        self.__buffer = b''
        self.__closed = False

    @property
    def conn(self) -> Union[socket.socket, ssl.SSLSocket]:
        if not isinstance(self.__conn, (socket.socket, ssl.SSLSocket)):
            raise TypeError('Connection is not a socket')

        if not self.__conn.fileno() > 0:
            raise ConnectionError('Connection is closed')

        return self.__conn

    @conn.setter
    def conn(self, conn: Union[socket.socket, ssl.SSLSocket]):
        if not isinstance(conn, (socket.socket, ssl.SSLSocket)):
            raise TypeError('Connection is not a socket')

        if not conn.fileno() > 0:
            raise ConnectionError('Connection is closed')

        self.__conn = conn

    @property
    def addr(self) -> Tuple[str, int]:
        return self.__addr

    @addr.setter
    def addr(self, addr: Tuple[str, int]):
        self.__addr = addr

    @property
    def buffer(self) -> bytes:
        return self.__buffer

    @buffer.setter
    def buffer(self, data: bytes) -> None:
        self.__buffer = data

    @property
    def closed(self) -> bool:
        return self.__closed

    @closed.setter
    def closed(self, value: bool) -> None:
        self.__closed = value

    def close(self):
        self.conn.close()
        self.closed = True

    def read(self, size: int = 4096) -> Optional[bytes]:
        data = self.conn.recv(size)
        return data if len(data) > 0 else None

    def write(self, data: Union[bytes, str]) -> int:
        if isinstance(data, str):
            data = data.encode()

        if len(data) <= 0:
            raise ValueError('Write data is empty')

        return self.conn.send(data)

    def queue(self, data: Union[bytes, str]) -> int:
        if isinstance(data, str):
            data = data.encode()

        if len(data) <= 0:
            raise ValueError('Queue data is empty')

        self.__buffer += data
        return len(data)

    def flush(self) -> int:
        sent = self.write(self.__buffer)
        self.__buffer = self.__buffer[sent:]
        return sent


class Client(Connection):
    def __str__(self):
        return f'Cliente - {self.addr[0]}:{self.addr[1]}'


class Server(Connection):
    def __str__(self):
        return f'Servidor - {self.addr[0]}:{self.addr[1]}'

    @classmethod
    def of(cls, addr: Tuple[str, int]) -> 'Server':
        return cls(socket.socket(socket.AF_INET, socket.SOCK_STREAM), addr)

    def connect(self, addr: Tuple[str, int] = None, timeout: int = 5) -> None:
        self.addr = addr or self.addr
        self.conn = socket.create_connection(self.addr, timeout)
        self.conn.settimeout(None)

        logger.info(f'{self} Conexão estabelecida')


class Proxy(threading.Thread):
    def __init__(self, client: Client, server: Optional[Server] = None) -> None:
        super().__init__()

        self.client = client
        self.server = server

        self.http_parser = HttpParser()

        self.__running = False

    @property
    def running(self) -> bool:
        if self.server and self.server.closed and self.client.closed:
            self.__running = False
        return self.__running

    @running.setter
    def running(self, value: bool) -> None:
        self.__running = value

    def _process_request(self, data: bytes) -> None:
        if self.server and not self.server.closed:
            self.server.queue(data)
            return

        self.http_parser.parse(data)

        if self.http_parser.method == 'CONNECT':
            host, port = self.http_parser.url.path.split(':')
        elif self.http_parser.url.hostname or self.http_parser.headers.get('Host'):
            host, port = (
                self.http_parser.url.hostname
                if not self.http_parser.headers.get('Host')
                else self.http_parser.headers['Host'],
                self.http_parser.url.port or REMOTE_ADDRESS[1],
            )
        else:
            raise ValueError('Invalid URL')

        self.server = Server.of((host, int(port)))
        self.server.connect()

        if (
            self.http_parser.method == 'CONNECT'
            or str(port) == '22'
            or str(port) == '443'
            or str(port) == '1194'
        ):
            self.client.queue(DEFAULT_RESPONSE)
        else:
            self.server.queue(self.http_parser.build())

        logger.info(f'{self.client} -> Solicitação: {self.http_parser.build()}')

    def _get_waitable_lists(self) -> Tuple[List[socket.socket]]:
        r, w, e = [self.client.conn], [], []

        if self.server and not self.server.closed:
            r.append(self.server.conn)

        if self.client.buffer:
            w.append(self.client.conn)

        if self.server and not self.server.closed and self.server.buffer:
            w.append(self.server.conn)

        return r, w, e

    def _process_wlist(self, wlist: List[socket.socket]) -> None:
        if self.client.conn in wlist:
            sent = self.client.flush()
            logger.debug(f'{self.client} enviou {sent} Bytes')

        if self.server and not self.server.closed and self.server.conn in wlist:
            sent = self.server.flush()
            logger.debug(f'{self.server} enviou {sent} Bytes')

    def _process_rlist(self, rlist: List[socket.socket]) -> None:
        if self.client.conn in rlist:
            data = self.client.read()
            self.running = data is not None
            if data and self.running:
                self._process_request(data)
                logger.debug(f'{self.client} recebeu {len(data)} Bytes')

        if self.server and not self.server.closed and self.server.conn in rlist:
            data = self.server.read()
            self.running = data is not None
            if data and self.running:
                self.client.queue(data)
                logger.debug(f'{self.server} recebeu {len(data)} Bytes')

    def _process(self) -> None:
        self.running = True

        while self.running:
            rlist, wlist, xlist = self._get_waitable_lists()
            r, w, _ = select.select(rlist, wlist, xlist, 1)

            self._process_wlist(w)
            self._process_rlist(r)

    def run(self) -> None:
        try:
            logger.info(f'{self.client} Conectado')
            self._process()
        except Exception as e:
            logger.error(f'{self.client} Erro: {e}')
        finally:
            self.client.close()
            if self.server and not self.server.closed:
                self.server.close()
            logger.info(f'{self.client} Desconectado')


class TCP:
    def __init__(self, addr: Tuple[str, int] = None, backlog: int = 5):
        self.__addr = addr
        self.__backlog = backlog

        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def handle(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        raise NotImplementedError()

    def run(self) -> None:
        self.__sock.bind(self.__addr)
        self.__sock.listen(self.__backlog)

        logger.info(f'Servidor iniciado em {self.__addr[0]}:{self.__addr[1]}')

        try:
            while True:
                conn, addr = self.__sock.accept()
                self.handle(conn, addr)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info('Finalizando servidor...')
            self.__sock.close()


class HTTP(TCP):
    def handle(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        client = Client(conn, addr)
        proxy = Proxy(client)
        proxy.daemon = True
        proxy.start()


class HTTPS(TCP):
    def __init__(self, addr: Tuple[str, int], cert: str, backlog: int = 5) -> None:
        super().__init__(addr, backlog)

        self.__cert = cert

    def handle_thread(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        conn = ssl.wrap_socket(
            sock=conn,
            keyfile=self.__cert,
            certfile=self.__cert,
            server_side=True,
            ssl_version=ssl.PROTOCOL_TLSv1_2,
        )

        client = Client(conn, addr)
        proxy = Proxy(client)
        proxy.daemon = True
        proxy.start()

    def handle(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        thread = threading.Thread(target=self.handle_thread, args=(conn, addr))
        thread.daemon = True
        thread.start()


def main():
    global REMOTE_ADDRESS
    
    parser = argparse.ArgumentParser(description='Proxy', usage='%(prog)s [options]')

    parser.add_argument('--host', default='0.0.0.0', help='Host')
    parser.add_argument('--port', type=int, default=8080, help='Port')
    parser.add_argument('--backlog', type=int, default=5, help='Backlog')
    parser.add_argument(
        '-r', '--remote', default='%s:%d' % (REMOTE_ADDRESS), help='Remote address, ex: 0.0.0.0:8080'
    )
    parser.add_argument('--cert', default='cert.pem', help='Certificate')

    parser.add_argument('--http', action='store_true', help='HTTP')
    parser.add_argument('--https', action='store_true', help='HTTPS')

    parser.add_argument('--log', default='INFO', help='Log level')
    parser.add_argument('--usage', action='store_true', help='Usage')

    args = parser.parse_args()

    if args.usage:
        print(usage)
        return

    if args.remote:
        REMOTE_ADDRESS = args.remote.split(':')[0], int(args.remote.split(':')[1])

    if args.http:
        server = HTTP((args.host, args.port), args.backlog)
    elif args.https:
        if not os.path.exists(args.cert):
            raise FileNotFoundError(f'Certicado {args.cert} não encontrado')
        server = HTTPS((args.host, args.port), args.cert, args.backlog)
    else:
        parser.print_help()
        return

    logging.basicConfig(
        level=getattr(logging, args.log.upper()),
        format='[%(asctime)s] %(levelname)s: %(message)s',
    )

    server.run()


if __name__ == '__main__':
    main()

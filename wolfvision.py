#!/usr/bin/env python3
import socket
import argparse
import sys


MSGLEN = 5


class WolfvisionClient:
    def __init__(self, options):
        self.options = options
        self.connect()
        method = getattr(self, f"run_{options.command}")
        method()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.options.device_ip, self.options.device_port))

    def run_get_streaming_state(self):
        print(f"Streaming status: {self.is_streaming()}")

    def is_streaming(self):
        self.send("08 CB20 00")
        response = self.receive(5)
        if response == "08cb200101":
            return True
        elif response == "08cb200100":
            return False
        else:
            raise Exception(f"Unexpected response to GET Streaming Mode : {response}")

    def check_response(self, msg, expected):
        assert msg == expected.lower().replace(" ", "")

    def run_start_streaming(self):
        if not self.is_streaming():
            self.send("09 CB20 01 01")
            response = self.receive(4)
            self.check_response(response, "09 CB20 00")
            assert self.is_streaming()
            print(f"Streaming started successfully, check rtsp://{self.options.device_ip}/stream")
        else:
            print("Already streaming")

    def run_stop_streaming(self):
        if self.is_streaming():
            self.send("09 CB20 01 00")
            response = self.receive(4)
            self.check_response(response, "09 CB20 00")
            assert not self.is_streaming()
            print("Streaming stopped successfully")
        else:
            print("Stream already stopped")

    def send(self, msg):
        data = bytes.fromhex(msg)
        self.sock.send(data)
        print(f"Sent {data}")

    def receive(self, buflen=4):
        return self.sock.recv(buflen).hex()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    commands = [
        "start_streaming",
        "stop_streaming",
        "get_streaming_state",
    ]

    parser.add_argument(
        "-c",
        "--command",
        type=str,
        required=True,
        help="Command among: %s" % (" ".join(commands))
    )

    parser.add_argument(
        "-d",
        "--device-ip",
        type=str,
        help="Cynap device IP",
        required=True,
    )

    parser.add_argument(
        "-p",
        "--device-port",
        type=int,
        help="Cynap device TCP port",
        default=50915,
    )

    args = parser.parse_args()

    if args.command not in commands:
        print(f"Invalid command {args.command}")
        parser.print_help()
        sys.exit(1)

    try:
        c = WolfvisionClient(args)
    except Exception as e:
        print("Exception occured: %s" % repr(e))
        sys.exit(1)

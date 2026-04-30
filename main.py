from ffb_driver import FanatecFFB
from socket_client import SocketClient

PROTOPIE_URL = "http://localhost:9981"
WHEEL_KEYWORD = "fanatec"


def main():
    print("=== ProtoPie -> Fanatec FFB Bridge ===")
    print(f"ProtoPie Connect: {PROTOPIE_URL}")
    print(f"Wheel keyword:    {WHEEL_KEYWORD}")
    print("--------------------------------------")

    ffb = FanatecFFB(wheel_keyword=WHEEL_KEYWORD)
    client = SocketClient(url=PROTOPIE_URL, ffb_driver=ffb)

    if not client.connect():
        print("[Main] Could not connect to ProtoPie Connect. Exiting.")
        ffb.stop()
        return

    try:
        client.wait()
    finally:
        ffb.stop()


if __name__ == "__main__":
    main()

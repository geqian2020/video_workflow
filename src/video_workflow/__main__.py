import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="启动本地卡通讲解工作台")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", type=Path, default=None)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv()
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()

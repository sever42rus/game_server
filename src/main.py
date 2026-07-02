import asyncio
import argparse
import ipaddress
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.application.game_service import GameService
from src.domain.models import WorldState
from src.domain.services import MovementService
from src.infrastructure.codec import GameProtocolCodec
from src.infrastructure.config import STATE_CHANGE_COOLDOWN_SECONDS
from src.infrastructure.server import GameServer
from src.infrastructure.sessions import SessionRegistry


def _parse_host(value: str) -> str:
    """Проверяет, что строка содержит корректный IPv4 или IPv6 адрес."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Некорректный IP-адрес: {value}",
        ) from error


def _parse_port(value: str) -> int:
    """Проверяет, что строка содержит TCP-порт в допустимом диапазоне."""
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Порт должен быть целым числом: {value}",
        ) from error

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            f"Порт должен быть в диапазоне 1..65535: {value}",
        )

    return port


def _build_argument_parser() -> argparse.ArgumentParser:
    """Создает парсер аргументов командной строки для запуска сервера."""
    parser = argparse.ArgumentParser(
        prog="game-server",
        description="Запускает TCP-сервер игрового мира.",
    )
    parser.add_argument(
        "--host",
        required=True,
        type=_parse_host,
        help="IPv4 или IPv6 адрес, на котором будет слушать сервер.",
    )
    parser.add_argument(
        "--port",
        required=True,
        type=_parse_port,
        help="TCP-порт сервера в диапазоне 1..65535.",
    )
    return parser


async def main(host: str, port: int) -> None:
    """Собирает зависимости сервера и запускает игровой процесс."""
    world = WorldState()
    movement = MovementService(
        state_change_cooldown_seconds=STATE_CHANGE_COOLDOWN_SECONDS,
    )
    game = GameService(world=world, movement=movement)
    server = GameServer(
        game=game,
        sessions=SessionRegistry(),
        codec=GameProtocolCodec(),
    )

    await server.start(host=host, port=port)


def run() -> None:
    """Запускает игровой сервер из консольной команды."""
    args = _build_argument_parser().parse_args()
    asyncio.run(main(host=args.host, port=args.port))


if __name__ == "__main__":
    run()

import asyncio
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


async def main():
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

    await server.start()


def run():
    """Запускает игровой сервер из консольной команды."""
    asyncio.run(main())


if __name__ == "__main__":
    run()

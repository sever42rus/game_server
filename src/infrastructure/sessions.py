import asyncio
from dataclasses import dataclass
from uuid import uuid4

from src.domain.models import PlayerId
from src.infrastructure.config import CLIENT_OUTGOING_QUEUE_SIZE


@dataclass
class ClientSession:
    """TCP-сессия клиента с персональной очередью исходящих сообщений."""

    player_id: PlayerId
    writer: asyncio.StreamWriter
    outgoing: asyncio.Queue[bytes]
    sender_task: asyncio.Task[None] | None = None


class SessionRegistry:
    """Хранилище соответствия TCP-соединений и игроков."""

    def __init__(
        self,
        outgoing_queue_size: int = CLIENT_OUTGOING_QUEUE_SIZE,
    ) -> None:
        """Создает пустой реестр клиентских сессий."""
        self._clients: dict[PlayerId, ClientSession] = {}
        self._writer_to_player_id: dict[int, PlayerId] = {}
        self._outgoing_queue_size = outgoing_queue_size

    def get_or_create_session(
        self,
        writer: asyncio.StreamWriter,
    ) -> tuple[ClientSession, bool]:
        """Возвращает TCP-сессию для соединения и признак новой сессии."""
        writer_key = id(writer)

        if writer_key in self._writer_to_player_id:
            player_id = self._writer_to_player_id[writer_key]
            return self._clients[player_id], False

        player_id = str(uuid4())
        session = ClientSession(
            player_id=player_id,
            writer=writer,
            outgoing=asyncio.Queue(maxsize=self._outgoing_queue_size),
        )
        self._writer_to_player_id[writer_key] = player_id
        self._clients[player_id] = session
        return session, True

    def unregister(self, player_id: PlayerId) -> None:
        """Удаляет TCP-сессию игрока из реестра подключений."""
        session = self._clients.pop(player_id, None)

        if session is None:
            return

        self._writer_to_player_id.pop(id(session.writer), None)

    def client_sessions(self) -> list[ClientSession]:
        """Возвращает список сессий всех подключенных клиентов."""
        return list(self._clients.values())

    def client_count(self) -> int:
        """Возвращает количество подключенных клиентских сессий."""
        return len(self._clients)

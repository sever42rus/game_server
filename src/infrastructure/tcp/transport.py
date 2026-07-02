import asyncio

from src.infrastructure.codec import GameProtocolCodec
from src.infrastructure.config import MAX_OUTGOING_MESSAGES_PER_BATCH
from src.infrastructure.sessions import ClientSession, SessionRegistry


class TcpPublisher:
    """
    Адаптер отправки исходящих сообщений через TCP-соединения.
    """

    def __init__(
        self,
        sessions: SessionRegistry,
        codec: GameProtocolCodec,
    ) -> None:
        """
        Создает TCP publisher с реестром сессий и кодеком игрового протокола.
        """
        self._sessions = sessions
        self._codec = codec

    async def send(
        self,
        writer: asyncio.StreamWriter,
        packet: bytes,
    ) -> None:
        """
        Отправляет один бинарный пакет конкретному TCP-клиенту.
        """
        writer.write(packet)
        await writer.drain()

    async def send_many(
        self,
        writer: asyncio.StreamWriter,
        packets: list[bytes],
    ) -> None:
        """Отправляет несколько бинарных пакетов одним TCP drain."""
        if not packets:
            return

        writer.write(b"".join(packets))
        await writer.drain()

    async def send_loop(self, session: ClientSession) -> None:
        """
        Отправляет сообщения из персональной очереди TCP-клиента.
        """
        while True:
            packet = await session.outgoing.get()
            packets = self._collect_outgoing_batch(session, packet)

            try:
                await self._send_batch(session.writer, packets)
            except (ConnectionError, OSError):
                return

    def broadcast(
        self,
        packet: bytes,
        excluded_player_ids: set[str] | None = None,
    ) -> None:
        """
        Ставит бинарный пакет в исходящие очереди всех подходящих клиентов.
        """
        excluded_player_ids = excluded_player_ids or set()

        for session in self._sessions.client_sessions():
            if session.player_id in excluded_player_ids:
                continue

            try:
                session.outgoing.put_nowait(packet)
            except asyncio.QueueFull:
                continue

    def _collect_outgoing_batch(
        self,
        session: ClientSession,
        first_packet: bytes,
    ) -> list[bytes]:
        """
        Собирает пачку исходящих сообщений из очереди клиента.
        """
        packets = [first_packet]

        for _ in range(MAX_OUTGOING_MESSAGES_PER_BATCH - 1):
            try:
                packets.append(session.outgoing.get_nowait())
            except asyncio.QueueEmpty:
                break

        return packets

    async def _send_batch(
        self,
        writer: asyncio.StreamWriter,
        packets: list[bytes],
    ) -> None:
        """
        Отправляет пачку бинарных пакетов одним TCP drain.
        """
        payload = b"".join(packets)
        writer.write(payload)
        await writer.drain()

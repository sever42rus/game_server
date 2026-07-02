import asyncio

from src.application.dto import (
    GameEventDTO,
    PlayerMoveStartedEventDTO,
    PlayerTargetSelectedEventDTO,
    PlayerUpdatedEventDTO,
)
from src.application.game_service import GameService
from src.domain.models import GameCommand, MoveCommand, PlayerId
from src.infrastructure.codec import GameProtocolCodec
from src.infrastructure.config import (
    COMMAND_QUEUE_SIZE,
    HOST,
    MAX_CATCH_UP_TICKS,
    MAX_COMMANDS_PER_TICK,
    PORT,
    TICK_RATE,
)
from src.infrastructure.sessions import SessionRegistry
from src.infrastructure.tcp.transport import TcpPublisher


class GameServer:
    """
    Композиционный корень игрового сервера и его фоновых циклов.
    """

    def __init__(
        self,
        game: GameService,
        sessions: SessionRegistry,
        codec: GameProtocolCodec,
    ) -> None:
        """
        Создает сервер и связывает application-сервис с TCP-инфраструктурой.
        """
        self._game = game
        self._sessions = sessions
        self._codec = codec
        self._incoming: asyncio.Queue[GameCommand] = asyncio.Queue(
            maxsize=COMMAND_QUEUE_SIZE,
        )
        self._publisher = TcpPublisher(sessions=sessions, codec=codec)

    async def start(self) -> None:
        """
        Запускает TCP-сервер и игровой цикл обработки команд.
        """
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(self._handle_loop_exception)
        server = await asyncio.start_server(
            self._handle_client,
            HOST,
            PORT,
        )

        print(f"TCP server started on {HOST}:{PORT}")
        asyncio.create_task(self._world_loop())

        async with server:
            await server.serve_forever()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Обрабатывает одно TCP-соединение клиента."""
        session, _ = self._sessions.get_or_create_session(writer)
        player_id = session.player_id
        peername = writer.get_extra_info("peername")
        player_joined = False

        print(f"player connected: {player_id} from {peername}")
        try:
            player_name = await self._read_player_name(reader)

            if player_name is None:
                return

            join_result = self._game.join_player(player_id, player_name)
            player_joined = True
            await self._publisher.send_many(
                writer,
                self._codec.world_snapshot_packets(join_result.snapshot),
            )
            session.sender_task = asyncio.create_task(
                self._publisher.send_loop(session),
            )
            self._publisher.broadcast(
                self._codec.player_spawned_packet(join_result),
                excluded_player_ids={player_id},
            )

            while True:
                packet = await self._read_incoming_packet(reader)

                if packet is None:
                    break

                command = self._codec.command_from_packet(player_id, packet)

                if command is None:
                    continue

                try:
                    self._incoming.put_nowait(command)
                except asyncio.QueueFull:
                    pass
        finally:
            self._sessions.unregister(player_id)
            player_removed = player_joined and self._game.leave_player(player_id)

            if player_removed:
                self._publisher.broadcast(
                    self._codec.player_disconnected_packet(player_id),
                )

            sender_task = session.sender_task

            if sender_task is not None:
                sender_task.cancel()

                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    print(f"sender task stopped with error: {exc}")

            await self._close_writer(writer)

            print(f"player disconnected: {player_id} from {peername}")

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        """
        Принудительно закрывает TCP writer для разорванного соединения.
        """
        writer.transport.abort()
        await asyncio.sleep(0)

    def _handle_loop_exception(
        self,
        loop: asyncio.AbstractEventLoop,
        context: dict[str, object],
    ) -> None:
        """
        Обрабатывает штатные сетевые ошибки event loop без шумного traceback.
        """
        exception = context.get("exception")

        if isinstance(exception, (BrokenPipeError, ConnectionResetError)):
            return

        loop.default_exception_handler(context)

    async def _world_loop(self) -> None:
        """
        Выполняет игровой цикл и рассылает обновления игроков по тикам.
        """
        tick_interval = 1 / TICK_RATE
        loop = asyncio.get_running_loop()
        next_tick_at = loop.time()
        catch_up_ticks = 0

        while True:
            outgoing_events: list[GameEventDTO] = []
            commands = self._read_commands_batch()
            coalesced_commands = self._coalesce_movement_commands(commands)

            for command in coalesced_commands:
                outgoing_events.extend(self._game.handle_command(command))

            outgoing_events.extend(self._game.tick(tick_interval))
            outgoing_events = self._coalesce_outgoing_events(outgoing_events)

            if outgoing_events:
                for packet in self._codec.world_delta_packets(outgoing_events):
                    self._publisher.broadcast(packet)

            next_tick_at += tick_interval
            sleep_seconds = next_tick_at - loop.time()

            if sleep_seconds > 0:
                catch_up_ticks = 0
                await asyncio.sleep(sleep_seconds)
                continue

            catch_up_ticks += 1

            if catch_up_ticks < MAX_CATCH_UP_TICKS:
                continue

            catch_up_ticks = 0
            next_tick_at = loop.time() + tick_interval
            await asyncio.sleep(tick_interval)

    async def _read_incoming_packet(
        self,
        reader: asyncio.StreamReader,
    ) -> bytes | None:
        """Читает один бинарный пакет клиента по заголовку и размеру payload."""
        try:
            opcode = await reader.readexactly(self._codec.incoming_opcode_size())
        except asyncio.IncompleteReadError:
            return None

        payload_size = self._codec.incoming_payload_size(opcode)

        if payload_size is not None:
            try:
                payload = await reader.readexactly(payload_size)
            except asyncio.IncompleteReadError:
                return None

            return opcode + payload

        try:
            payload_header_size = self._codec.incoming_variable_payload_header_size(
                opcode,
            )
        except ValueError:
            return None

        try:
            payload_header = await reader.readexactly(payload_header_size)
        except asyncio.IncompleteReadError:
            return None

        try:
            payload_size = self._codec.incoming_variable_payload_size(
                opcode,
                payload_header,
            )
        except ValueError:
            return None

        if payload_size is None:
            return None

        remaining_payload_size = payload_size - len(payload_header)

        try:
            payload_body = await reader.readexactly(remaining_payload_size)
        except asyncio.IncompleteReadError:
            return None

        return opcode + payload_header + payload_body

    async def _read_player_name(self, reader: asyncio.StreamReader) -> str | None:
        """Читает обязательный стартовый пакет имени перед входом игрока в мир."""
        packet = await self._read_incoming_packet(reader)

        if packet is None:
            return None

        return self._codec.player_name_from_packet(packet)

    def _read_commands_batch(self) -> list[GameCommand]:
        """
        Вычитывает ограниченную пачку входящих команд из очереди.
        """
        commands = []

        for _ in range(MAX_COMMANDS_PER_TICK):
            try:
                command = self._incoming.get_nowait()
            except asyncio.QueueEmpty:
                break

            commands.append(command)

        return commands

    def _coalesce_movement_commands(
        self,
        commands: list[GameCommand],
    ) -> list[GameCommand]:
        """
        Сжимает команды движения, оставляя последнее движение игрока в сегменте.
        """
        coalesced_commands: list[GameCommand] = []
        pending_moves: dict[PlayerId, MoveCommand] = {}

        for command in commands:
            if isinstance(command, MoveCommand):
                pending_moves.pop(command.player_id, None)
                pending_moves[command.player_id] = command
                continue

            self._flush_pending_moves(pending_moves, coalesced_commands)
            coalesced_commands.append(command)

        self._flush_pending_moves(pending_moves, coalesced_commands)

        return coalesced_commands

    def _flush_pending_moves(
        self,
        pending_moves: dict[PlayerId, MoveCommand],
        coalesced_commands: list[GameCommand],
    ) -> None:
        """
        Переносит накопленные команды движения в итоговую пачку команд.
        """
        coalesced_commands.extend(pending_moves.values())
        pending_moves.clear()

    def _coalesce_outgoing_events(
        self,
        events: list[GameEventDTO],
    ) -> list[GameEventDTO]:
        """
        Сжимает исходящие события, оставляя последнее событие типа за тик.
        """
        coalesced_events: dict[tuple[PlayerId, type], GameEventDTO] = {}

        for event in events:
            player_id = self._player_id_from_event(event)

            if player_id is None:
                continue

            event_key = (player_id, type(event))
            coalesced_events.pop(event_key, None)
            coalesced_events[event_key] = event

        return list(coalesced_events.values())

    def _player_id_from_event(self, event: GameEventDTO) -> PlayerId | None:
        """
        Возвращает идентификатор игрока из исходящего игрового события.
        """
        if isinstance(event, PlayerUpdatedEventDTO):
            return event.player.id

        if isinstance(event, PlayerMoveStartedEventDTO):
            return event.movement.id

        if isinstance(event, PlayerTargetSelectedEventDTO):
            return event.target.id

        return None

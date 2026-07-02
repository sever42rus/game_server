from enum import IntEnum, IntFlag
from typing import Any
from uuid import UUID

from src.application.dto import (
    GameEventDTO,
    JoinPlayerResultDTO,
    PlayerDTO,
    PlayerMoveStartedEventDTO,
    PlayerMovementDTO,
    PlayerTargetDTO,
    PlayerTargetSelectedEventDTO,
    PlayerUpdatedEventDTO,
    TargetDTO,
    WorldSnapshotDTO,
)
from src.domain.models import (
    CharacterState,
    GameCommand,
    MoveCommand,
    PlayerId,
    Position,
    SelectTargetCommand,
    StateCommand,
    TargetRef,
    TargetType,
)
from src.infrastructure.packet import PacketReader, PacketWriter


class IncomingPacketOpcode(IntEnum):
    """Коды входящих пакетов клиента.

    Значения:
    - `0x0100` — передача имени перед входом в мир.
    - `0x0101` — запуск движения к целевой точке.
    - `0x0102` — перевод персонажа в состояние `standing`.
    - `0x0103` — перевод персонажа в состояние `sitting`.
    - `0x0104` — выбор цели в мире.
    - `0x0105` — сброс текущей выбранной цели.
    """

    SET_NAME = 0x0100
    MOVE = 0x0101
    STAND = 0x0102
    SIT = 0x0103
    SELECT_TARGET = 0x0104
    CLEAR_TARGET = 0x0105


class IncomingMovementCode(IntEnum):
    """Коды входящего режима движения.

    Значения:
    - `1` — движение шагом.
    - `2` — движение бегом.
    """

    WALK = 1
    RUN = 2


class IncomingTargetTypeCode(IntEnum):
    """Коды входящего типа цели.

    Значения:
    - `1` — целью выбран другой игрок.
    """

    PLAYER = 1


class OutgoingPacketOpcode(IntEnum):
    """Коды исходящих пакетов сервера.

    Значения:
    - `0x0201` — идентификатор локального игрока клиента.
    - `0x0202` — создание игрока в локальном мире клиента.
    - `0x0203` — завершение начальной передачи видимых игроков.
    - `0x0204` — появление нового игрока после инициализации.
    - `0x0205` — начало движения игрока.
    - `0x0206` — точное обновление состояния игрока.
    - `0x0207` — выбор или сброс цели игрока.
    - `0x0208` — удаление игрока из локального мира клиента.
    """

    OWN_PLAYER = 0x0201
    PLAYER_SPAWN = 0x0202
    SNAPSHOT_END = 0x0203
    PLAYER_SPAWNED = 0x0204
    PLAYER_MOVE_STARTED = 0x0205
    PLAYER_UPDATED = 0x0206
    PLAYER_TARGET_CHANGED = 0x0207
    PLAYER_DISCONNECTED = 0x0208


class OutgoingCharacterStateCode(IntEnum):
    """Коды исходящего состояния персонажа.

    Значения:
    - `1` — персонаж стоит.
    - `2` — персонаж идет.
    - `3` — персонаж бежит.
    - `4` — персонаж сидит.
    """

    STANDING = 1
    WALKING = 2
    RUNNING = 3
    SITTING = 4


class OutgoingTargetTypeCode(IntEnum):
    """Коды исходящего типа цели.

    Значения:
    - `1` — целью является игрок.
    """

    PLAYER = 1


class OutgoingPlayerSpawnFlags(IntFlag):
    """Флаги дополнительных полей в пакете создания игрока.

    Значения:
    - `1` — у игрока выбрана цель.
    - `2` — игрок уже движется к целевой точке.
    """

    HAS_TARGET = 1
    HAS_MOVEMENT_TARGET = 2


class OutgoingTargetFlags(IntFlag):
    """Флаги пакета изменения выбранной цели.

    Значения:
    - `1` — у игрока после обновления есть выбранная цель.
    """

    HAS_TARGET = 1


class GameProtocolCodec:
    """Кодек бинарных входящих и исходящих пакетов игрового мира."""

    _OPCODE_SIZE_BYTES = 2
    _NAME_LENGTH_SIZE_BYTES = 1
    _MAX_PLAYER_NAME_BYTES = 24
    _INCOMING_PAYLOAD_SIZES: dict[IncomingPacketOpcode, int] = {
        IncomingPacketOpcode.MOVE: 9,
        IncomingPacketOpcode.STAND: 0,
        IncomingPacketOpcode.SIT: 0,
        IncomingPacketOpcode.SELECT_TARGET: 17,
        IncomingPacketOpcode.CLEAR_TARGET: 0,
    }

    def incoming_opcode_size(self) -> int:
        """Возвращает размер заголовка с кодом входящего пакета."""
        return self._OPCODE_SIZE_BYTES

    def incoming_payload_size(self, opcode_bytes: bytes) -> int | None:
        """Возвращает размер payload для указанного бинарного `opcode`."""
        try:
            opcode = self._incoming_opcode_from_bytes(opcode_bytes)
        except ValueError:
            return None

        if opcode == IncomingPacketOpcode.SET_NAME:
            return None

        return self._INCOMING_PAYLOAD_SIZES.get(opcode)

    def incoming_variable_payload_header_size(self, opcode_bytes: bytes) -> int:
        """Возвращает размер служебного заголовка переменного payload по `opcode`."""
        opcode = self._incoming_opcode_from_bytes(opcode_bytes)

        if opcode == IncomingPacketOpcode.SET_NAME:
            return self._NAME_LENGTH_SIZE_BYTES

        return 0

    def incoming_variable_payload_size(
        self,
        opcode_bytes: bytes,
        payload_header: bytes,
    ) -> int | None:
        """Возвращает полный размер переменного payload по его служебному заголовку."""
        opcode = self._incoming_opcode_from_bytes(opcode_bytes)

        if opcode != IncomingPacketOpcode.SET_NAME:
            return None

        if len(payload_header) != self._NAME_LENGTH_SIZE_BYTES:
            return None

        name_length = payload_header[0]

        if name_length == 0 or name_length > self._MAX_PLAYER_NAME_BYTES:
            return None

        return self._NAME_LENGTH_SIZE_BYTES + name_length

    def player_name_from_packet(self, packet: bytes) -> str | None:
        """Извлекает и валидирует имя игрока из входящего пакета `SET_NAME`."""
        try:
            reader = PacketReader(packet)
            opcode = IncomingPacketOpcode(reader.read_short())
        except ValueError:
            return None

        if opcode != IncomingPacketOpcode.SET_NAME:
            return None

        try:
            return self._player_name_from_reader(reader)
        except ValueError:
            return None

    def command_from_packet(
        self,
        player_id: PlayerId,
        packet: bytes,
    ) -> GameCommand | None:
        """Создает игровую команду из входящего бинарного пакета клиента."""
        try:
            reader = PacketReader(packet)
            opcode = IncomingPacketOpcode(reader.read_short())
        except ValueError:
            return None

        try:
            if opcode == IncomingPacketOpcode.MOVE:
                return self._move_command_from_reader(player_id, reader)

            if opcode == IncomingPacketOpcode.STAND:
                return self._state_command_from_opcode(player_id, opcode, reader)

            if opcode == IncomingPacketOpcode.SIT:
                return self._state_command_from_opcode(player_id, opcode, reader)

            if opcode == IncomingPacketOpcode.SELECT_TARGET:
                return self._select_target_command_from_reader(player_id, reader)

            if opcode == IncomingPacketOpcode.CLEAR_TARGET:
                return self._clear_target_command_from_reader(player_id, reader)
        except ValueError:
            return None

        return None

    def own_player_packet(self, player_id: PlayerId) -> bytes:
        """Создает пакет идентификатора локального игрока для нового клиента."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.OWN_PLAYER)
        writer.write_uuid(self._uuid_from_player_id(player_id))
        return writer.to_bytes()

    def world_snapshot_packets(self, snapshot: WorldSnapshotDTO) -> list[bytes]:
        """Создает серию пакетов начального состояния видимого мира клиента."""
        packets = [self.own_player_packet(snapshot.your_id)]

        for player_id, player in snapshot.players.items():
            packets.append(self._snapshot_player_packet(player_id, player))

        packets.append(self.snapshot_end_packet())
        return packets

    def snapshot_end_packet(self) -> bytes:
        """Создает пакет завершения начальной передачи видимого мира."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.SNAPSHOT_END)
        return writer.to_bytes()

    def player_spawned_packet(self, result: JoinPlayerResultDTO) -> bytes:
        """Создает пакет появления нового игрока для уже подключенных клиентов."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.PLAYER_SPAWNED)
        self._write_player_core(
            writer=writer,
            player_id=result.joined_player.id,
            x=result.joined_player.x,
            y=result.joined_player.y,
            speed=result.joined_player.speed,
            state=result.joined_player.state,
        )
        self._write_player_name(writer, result.joined_player.name)
        return writer.to_bytes()

    def player_disconnected_packet(self, player_id: PlayerId) -> bytes:
        """Создает пакет удаления игрока из локального мира клиента."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.PLAYER_DISCONNECTED)
        writer.write_uuid(self._uuid_from_player_id(player_id))
        return writer.to_bytes()

    def player_update_packet(self, player: PlayerDTO) -> bytes:
        """Создает пакет точного обновления состояния игрока."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.PLAYER_UPDATED)
        self._write_player_core(
            writer=writer,
            player_id=player.id,
            x=player.x,
            y=player.y,
            speed=player.speed,
            state=player.state,
        )
        return writer.to_bytes()

    def player_move_started_packet(self, movement: PlayerMovementDTO) -> bytes:
        """Создает пакет начала движения игрока к целевой точке."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.PLAYER_MOVE_STARTED)
        self._write_player_core(
            writer=writer,
            player_id=movement.id,
            x=movement.x,
            y=movement.y,
            speed=movement.speed,
            state=movement.state,
        )
        writer.write_int(movement.target_x)
        writer.write_int(movement.target_y)
        return writer.to_bytes()

    def player_target_changed_packet(self, target: PlayerTargetDTO) -> bytes:
        """Создает пакет выбора или сброса цели игрока."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.PLAYER_TARGET_CHANGED)
        writer.write_uuid(self._uuid_from_player_id(target.id))

        flags = OutgoingTargetFlags(0)

        if target.selected_target is not None:
            flags |= OutgoingTargetFlags.HAS_TARGET

        writer.write_byte(flags)

        if target.selected_target is not None:
            writer.write_byte(self._outgoing_target_type_code(target.selected_target.type))
            writer.write_uuid(self._uuid_from_player_id(target.selected_target.id))

        return writer.to_bytes()

    def event_packets(self, event: GameEventDTO) -> list[bytes]:
        """Создает один или несколько исходящих пакетов из игрового события."""
        if isinstance(event, PlayerUpdatedEventDTO):
            return [self.player_update_packet(event.player)]

        if isinstance(event, PlayerMoveStartedEventDTO):
            return [self.player_move_started_packet(event.movement)]

        if isinstance(event, PlayerTargetSelectedEventDTO):
            return [self.player_target_changed_packet(event.target)]

        raise TypeError(f"Unsupported game event: {event!r}")

    def world_delta_packets(self, events: list[GameEventDTO]) -> list[bytes]:
        """Создает линейный набор пакетов из пачки игровых событий мира."""
        packets: list[bytes] = []

        for event in events:
            packets.extend(self.event_packets(event))

        return packets

    def _move_command_from_reader(
        self,
        player_id: PlayerId,
        reader: PacketReader,
    ) -> MoveCommand | None:
        """Создает команду движения из payload пакета `MOVE`."""
        x = reader.read_int()
        y = reader.read_int()
        state = self._movement_state_from_code(reader.read_byte())

        if state is None or reader.remaining() != 0:
            return None

        return MoveCommand(
            player_id=player_id,
            target=Position(x=x, y=y),
            state=state,
        )

    def _state_command_from_opcode(
        self,
        player_id: PlayerId,
        opcode: IncomingPacketOpcode,
        reader: PacketReader,
    ) -> StateCommand | None:
        """Создает команду смены состояния из пакета без payload."""
        if reader.remaining() != 0:
            return None

        if opcode == IncomingPacketOpcode.STAND:
            return StateCommand(
                player_id=player_id,
                state=CharacterState.STANDING,
            )

        if opcode == IncomingPacketOpcode.SIT:
            return StateCommand(
                player_id=player_id,
                state=CharacterState.SITTING,
            )

        return None

    def _select_target_command_from_reader(
        self,
        player_id: PlayerId,
        reader: PacketReader,
    ) -> SelectTargetCommand | None:
        """Создает команду выбора цели из payload пакета `SELECT_TARGET`."""
        target_type = self._target_type_from_code(reader.read_byte())
        target_id = str(reader.read_uuid())

        if target_type is None or reader.remaining() != 0:
            return None

        return SelectTargetCommand(
            player_id=player_id,
            target=TargetRef(type=target_type, id=target_id),
        )

    def _clear_target_command_from_reader(
        self,
        player_id: PlayerId,
        reader: PacketReader,
    ) -> SelectTargetCommand | None:
        """Создает команду сброса выбранной цели из пакета `CLEAR_TARGET`."""
        if reader.remaining() != 0:
            return None

        return SelectTargetCommand(player_id=player_id, target=None)

    def _player_name_from_reader(self, reader: PacketReader) -> str:
        """Читает имя игрока из payload пакета `SET_NAME`."""
        name_length = reader.read_byte()
        name_bytes = reader.read_bytes(name_length)

        if reader.remaining() != 0:
            raise ValueError("SET_NAME packet contains unexpected trailing bytes")

        return self._validate_player_name(name_bytes)

    def _snapshot_player_packet(
        self,
        player_id: PlayerId,
        player: dict[str, Any],
    ) -> bytes:
        """Создает пакет начального создания игрока из словаря снимка мира."""
        writer = PacketWriter()
        writer.write_short(OutgoingPacketOpcode.PLAYER_SPAWN)
        self._write_player_core(
            writer=writer,
            player_id=player_id,
            x=self._snapshot_int(player, "x"),
            y=self._snapshot_int(player, "y"),
            speed=self._snapshot_int(player, "speed"),
            state=self._snapshot_str(player, "state"),
        )
        self._write_player_name(writer, self._snapshot_str(player, "name"))
        flags = self._spawn_flags_from_snapshot(player)
        writer.write_byte(flags)
        self._write_snapshot_target(writer, player, flags)
        self._write_snapshot_movement_target(writer, player, flags)
        return writer.to_bytes()

    def _write_player_core(
        self,
        writer: PacketWriter,
        player_id: PlayerId,
        x: int,
        y: int,
        speed: float,
        state: str,
    ) -> None:
        """Записывает общие поля состояния игрока в исходящий пакет."""
        writer.write_uuid(self._uuid_from_player_id(player_id))
        writer.write_int(x)
        writer.write_int(y)
        writer.write_int(int(round(speed)))
        writer.write_byte(self._outgoing_state_code(state))

    def _write_player_name(self, writer: PacketWriter, name: str) -> None:
        """Записывает имя игрока в исходящий пакет с префиксом длины."""
        encoded_name = name.encode("utf-8")

        if not encoded_name or len(encoded_name) > self._MAX_PLAYER_NAME_BYTES:
            raise ValueError("Outgoing player name has unsupported length")

        writer.write_byte(len(encoded_name))
        writer.write_utf8(name)

    def _spawn_flags_from_snapshot(
        self,
        player: dict[str, Any],
    ) -> OutgoingPlayerSpawnFlags:
        """Вычисляет флаги дополнительных полей для пакета начального спавна."""
        flags = OutgoingPlayerSpawnFlags(0)

        if player.get("selected_target") is not None:
            flags |= OutgoingPlayerSpawnFlags.HAS_TARGET

        if "target_x" in player and "target_y" in player:
            flags |= OutgoingPlayerSpawnFlags.HAS_MOVEMENT_TARGET

        return flags

    def _write_snapshot_target(
        self,
        writer: PacketWriter,
        player: dict[str, Any],
        flags: OutgoingPlayerSpawnFlags,
    ) -> None:
        """Записывает выбранную цель игрока в пакет начального спавна."""
        if not flags & OutgoingPlayerSpawnFlags.HAS_TARGET:
            return

        target = player.get("selected_target")

        if not isinstance(target, dict):
            raise ValueError("Snapshot target payload must be a mapping")

        target_type = target.get("type")
        target_id = target.get("id")

        if not isinstance(target_type, str) or not isinstance(target_id, str):
            raise ValueError("Snapshot target fields must be strings")

        writer.write_byte(self._outgoing_target_type_code(target_type))
        writer.write_uuid(self._uuid_from_player_id(target_id))

    def _write_snapshot_movement_target(
        self,
        writer: PacketWriter,
        player: dict[str, Any],
        flags: OutgoingPlayerSpawnFlags,
    ) -> None:
        """Записывает целевую точку движения игрока в пакет начального спавна."""
        if not flags & OutgoingPlayerSpawnFlags.HAS_MOVEMENT_TARGET:
            return

        writer.write_int(self._snapshot_int(player, "target_x"))
        writer.write_int(self._snapshot_int(player, "target_y"))

    def _snapshot_int(self, player: dict[str, Any], key: str) -> int:
        """Читает целочисленное поле из словаря снимка мира."""
        value = player.get(key)

        if isinstance(value, bool):
            raise ValueError(f"Snapshot field {key!r} must not be bool")

        if not isinstance(value, (int, float)):
            raise ValueError(f"Snapshot field {key!r} must be numeric")

        return int(round(value))

    def _snapshot_str(self, player: dict[str, Any], key: str) -> str:
        """Читает строковое поле из словаря снимка мира."""
        value = player.get(key)

        if not isinstance(value, str):
            raise ValueError(f"Snapshot field {key!r} must be a string")

        return value

    def _validate_player_name(self, name_bytes: bytes) -> str:
        """Проверяет длину и содержимое имени игрока из транспортного пакета."""
        if not name_bytes or len(name_bytes) > self._MAX_PLAYER_NAME_BYTES:
            raise ValueError("Player name length is invalid")

        try:
            name = name_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Player name must be valid UTF-8") from exc

        name = name.strip()

        if not name:
            raise ValueError("Player name must not be blank")

        if len(name.encode("utf-8")) > self._MAX_PLAYER_NAME_BYTES:
            raise ValueError("Player name is too long after normalization")

        return name

    def _incoming_opcode_from_bytes(self, opcode_bytes: bytes) -> IncomingPacketOpcode:
        """Преобразует бинарный заголовок пакета в enum кода входящей команды."""
        if len(opcode_bytes) != self._OPCODE_SIZE_BYTES:
            raise ValueError("Opcode header size is invalid")

        return IncomingPacketOpcode(
            int.from_bytes(opcode_bytes, byteorder="little", signed=False),
        )

    def _movement_state_from_code(self, code: int) -> CharacterState | None:
        """Преобразует числовой код режима движения в доменное состояние."""
        if code == IncomingMovementCode.RUN:
            return CharacterState.RUNNING

        if code == IncomingMovementCode.WALK:
            return CharacterState.WALKING

        return None

    def _target_type_from_code(self, code: int) -> TargetType | None:
        """Преобразует числовой код типа цели в доменный тип."""
        if code == IncomingTargetTypeCode.PLAYER:
            return TargetType.PLAYER

        return None

    def _outgoing_state_code(self, state: str) -> int:
        """Преобразует строковое состояние персонажа в числовой код протокола."""
        mapping = {
            CharacterState.STANDING.value: OutgoingCharacterStateCode.STANDING,
            CharacterState.WALKING.value: OutgoingCharacterStateCode.WALKING,
            CharacterState.RUNNING.value: OutgoingCharacterStateCode.RUNNING,
            CharacterState.SITTING.value: OutgoingCharacterStateCode.SITTING,
        }
        code = mapping.get(state)

        if code is None:
            raise ValueError(f"Unsupported outgoing character state: {state!r}")

        return int(code)

    def _outgoing_target_type_code(self, target_type: str) -> int:
        """Преобразует строковый тип цели в числовой код исходящего протокола."""
        if target_type == TargetType.PLAYER.value:
            return int(OutgoingTargetTypeCode.PLAYER)

        raise ValueError(f"Unsupported outgoing target type: {target_type!r}")

    def _uuid_from_player_id(self, player_id: PlayerId) -> UUID:
        """Преобразует строковый идентификатор игрока в бинарный UUID протокола."""
        return UUID(player_id)

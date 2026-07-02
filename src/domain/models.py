from dataclasses import dataclass, field
from enum import StrEnum


PlayerId = str


class CharacterState(StrEnum):
    """Состояние персонажа в игровом мире."""

    STANDING = "standing"
    WALKING = "walking"
    RUNNING = "running"
    SITTING = "sitting"


class TargetType(StrEnum):
    """Тип выбранной цели в игровом мире."""

    PLAYER = "player"


@dataclass
class Position:
    """Координаты сущности в игровом мире."""

    x: float
    y: float

    def rounded(self) -> dict[str, int]:
        """Возвращает координаты, округленные до целых чисел для исходящих данных."""
        return {
            "x": int(round(self.x)),
            "y": int(round(self.y)),
        }


@dataclass
class Player:
    """Игрок, состояние которого хранится на сервере."""

    id: PlayerId
    name: str
    position: Position
    speed: int = 100
    state: CharacterState = CharacterState.STANDING
    target_position: Position | None = None
    selected_target: "TargetRef | None" = None
    state_change_locked_until: float = 0.0

    def current_speed(self) -> float:
        """Возвращает текущую скорость игрока с учетом режима движения."""
        if self.state == CharacterState.WALKING:
            return self.speed / 2

        return self.speed

    def can_transition_to(
        self,
        state: CharacterState,
        current_time: float,
    ) -> bool:
        """Проверяет, допустим ли переход игрока в указанное состояние."""
        if self._is_state_change_locked(state, current_time):
            return False

        if self.state == state:
            return state != CharacterState.SITTING

        if self.state == CharacterState.SITTING:
            return state == CharacterState.STANDING

        if state == CharacterState.SITTING:
            return self.state == CharacterState.STANDING

        return True

    def apply_state(
        self,
        state: CharacterState,
        current_time: float,
        lock_duration_seconds: float,
    ) -> None:
        """Применяет новое состояние и обновляет блокировку смены состояния."""
        previous_state = self.state
        self.state = state

        if self._should_lock_state_change(previous_state, state):
            self.state_change_locked_until = current_time + lock_duration_seconds

    def _is_state_change_locked(
        self,
        state: CharacterState,
        current_time: float,
    ) -> bool:
        """Проверяет, действует ли блокировка на смену состояния игрока."""
        return state != self.state and current_time < self.state_change_locked_until

    def _should_lock_state_change(
        self,
        previous_state: CharacterState,
        new_state: CharacterState,
    ) -> bool:
        """Проверяет, нужно ли запускать блокировку после смены состояния."""
        stand_sit_transitions = {
            (CharacterState.STANDING, CharacterState.SITTING),
            (CharacterState.SITTING, CharacterState.STANDING),
        }
        return (previous_state, new_state) in stand_sit_transitions


@dataclass(frozen=True)
class TargetRef:
    """Ссылка на выбранную цель в игровом мире."""

    type: TargetType
    id: PlayerId


@dataclass(frozen=True)
class MoveCommand:
    """Команда перемещения игрока в заданную точку."""

    player_id: PlayerId
    target: Position
    state: CharacterState


@dataclass(frozen=True)
class StateCommand:
    """Команда смены состояния персонажа с остановкой движения."""

    player_id: PlayerId
    state: CharacterState


@dataclass(frozen=True)
class SelectTargetCommand:
    """Команда выбора или сброса цели игрока."""

    player_id: PlayerId
    target: TargetRef | None


GameCommand = MoveCommand | StateCommand | SelectTargetCommand


@dataclass(frozen=True)
class PlayerUpdate:
    """Изменение состояния игрока после обработки команды."""

    player_id: PlayerId
    position: Position
    state: CharacterState


@dataclass(frozen=True)
class PlayerMovement:
    """Данные о начатом перемещении игрока к целевой точке."""

    player_id: PlayerId
    position: Position
    target: Position
    speed: float
    state: CharacterState


@dataclass
class WorldState:
    """Состояние игрового мира, независимое от транспорта и формата сообщений."""

    players: dict[PlayerId, Player] = field(default_factory=dict)

    def add_player(
        self,
        player_id: PlayerId,
        name: str,
        position: Position,
        speed: int = 100,
    ) -> Player:
        """Добавляет игрока в мир и возвращает созданную доменную сущность."""
        player = Player(id=player_id, name=name, position=position, speed=speed)
        self.players[player_id] = player
        return player

    def get_player(self, player_id: PlayerId) -> Player | None:
        """Возвращает игрока по идентификатору, если он есть в мире."""
        return self.players.get(player_id)

    def remove_player(self, player_id: PlayerId) -> Player | None:
        """Удаляет игрока из мира и возвращает его, если он существовал."""
        return self.players.pop(player_id, None)

    def has_player(self, player_id: PlayerId) -> bool:
        """Проверяет, зарегистрирован ли игрок в игровом мире."""
        return player_id in self.players

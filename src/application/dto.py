from dataclasses import dataclass

from src.domain.models import PlayerId


@dataclass(frozen=True)
class TargetDTO:
    """DTO выбранной цели игрока для клиентского протокола."""

    type: str
    id: PlayerId


@dataclass(frozen=True)
class PlayerDTO:
    """DTO игрока для передачи данных между приложением и инфраструктурой."""

    id: PlayerId
    name: str
    x: int
    y: int
    speed: float
    state: str


@dataclass(frozen=True)
class PlayerMovementDTO:
    """DTO начатого перемещения игрока к целевой точке."""

    id: PlayerId
    x: int
    y: int
    target_x: int
    target_y: int
    speed: float
    state: str


@dataclass(frozen=True)
class PlayerTargetDTO:
    """DTO выбранной цели игрока."""

    id: PlayerId
    selected_target: TargetDTO | None


@dataclass(frozen=True)
class WorldSnapshotDTO:
    """DTO снимка мира, который отправляется новому клиенту."""

    your_id: PlayerId
    players: dict[PlayerId, dict[str, float | int | str | dict[str, str] | None]]


@dataclass(frozen=True)
class JoinPlayerResultDTO:
    """DTO результата подключения игрока к игровому миру."""

    snapshot: WorldSnapshotDTO
    joined_player: PlayerDTO


@dataclass(frozen=True)
class PlayerUpdatedEventDTO:
    """DTO события обновления состояния игрока."""

    player: PlayerDTO


@dataclass(frozen=True)
class PlayerMoveStartedEventDTO:
    """DTO события начала перемещения игрока."""

    movement: PlayerMovementDTO


@dataclass(frozen=True)
class PlayerTargetSelectedEventDTO:
    """DTO события выбора или сброса цели игрока."""

    target: PlayerTargetDTO


GameEventDTO = (
    PlayerUpdatedEventDTO | PlayerMoveStartedEventDTO | PlayerTargetSelectedEventDTO
)

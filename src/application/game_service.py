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
    GameCommand,
    MoveCommand,
    Player,
    PlayerId,
    Position,
    SelectTargetCommand,
    StateCommand,
    TargetRef,
    TargetType,
    WorldState,
)
from src.domain.services import MovementService


class GameService:
    """Сервис сценариев игры, который координирует доменную модель."""

    def __init__(self, world: WorldState, movement: MovementService) -> None:
        """Создает сервис игры с переданным состоянием мира и сервисом движения."""
        self._world = world
        self._movement = movement
        self._elapsed_time = 0.0

    def join_player(self, player_id: PlayerId, name: str) -> JoinPlayerResultDTO:
        """Подключает игрока к миру и возвращает данные для стартовых сообщений."""
        player = self._world.get_player(player_id)

        if player is None:
            player = self._world.add_player(player_id, name, Position(x=0, y=0))
        else:
            player.name = name

        player_dto = self._player_dto(player)

        return JoinPlayerResultDTO(
            snapshot=WorldSnapshotDTO(
                your_id=player.id,
                players=self._players_snapshot(),
            ),
            joined_player=player_dto,
        )

    def leave_player(self, player_id: PlayerId) -> bool:
        """Удаляет игрока из мира и возвращает признак успешного удаления."""
        player_removed = self._world.remove_player(player_id) is not None

        if player_removed:
            self._clear_removed_player_targets(player_id)

        return player_removed

    def handle_command(self, command: GameCommand) -> list[GameEventDTO]:
        """Обрабатывает игровую команду и возвращает события для клиентов."""
        if isinstance(command, StateCommand):
            player_update = self.change_state(command)

            if player_update is None:
                return []

            return [PlayerUpdatedEventDTO(player=player_update)]

        if isinstance(command, SelectTargetCommand):
            target = self.select_target(command)

            if target is None:
                return []

            return [PlayerTargetSelectedEventDTO(target=target)]

        movement = self.start_movement(command)

        if movement is None:
            return []

        events: list[GameEventDTO] = []
        target = self._clear_target_after_movement_started(command.player_id)

        if target is not None:
            events.append(PlayerTargetSelectedEventDTO(target=target))

        events.append(PlayerMoveStartedEventDTO(movement=movement))

        return events

    def start_movement(self, command: MoveCommand) -> PlayerMovementDTO | None:
        """Запускает перемещение игрока к заданной точке."""
        player = self._world.get_player(command.player_id)

        if player is None:
            return None

        movement = self._movement.set_target(
            player,
            command.target,
            command.state,
            self._elapsed_time,
        )

        if movement is None:
            return None

        return PlayerMovementDTO(
            id=movement.player_id,
            x=int(round(movement.position.x)),
            y=int(round(movement.position.y)),
            target_x=int(round(movement.target.x)),
            target_y=int(round(movement.target.y)),
            speed=movement.speed,
            state=movement.state.value,
        )

    def tick(self, tick_seconds: float) -> list[GameEventDTO]:
        """Выполняет один тик симуляции и возвращает события для клиентов."""
        self._elapsed_time += tick_seconds
        events: list[GameEventDTO] = []

        for player in self._world.players.values():
            update = self._movement.tick(player, tick_seconds)

            if update is not None:
                events.append(
                    PlayerUpdatedEventDTO(
                        player=PlayerDTO(
                            id=update.player_id,
                            name=player.name,
                            x=int(round(update.position.x)),
                            y=int(round(update.position.y)),
                            speed=player.current_speed(),
                            state=update.state.value,
                        ),
                    ),
                )

        return events

    def change_state(self, command: StateCommand) -> PlayerDTO | None:
        """Останавливает игрока и меняет состояние персонажа."""
        player = self._world.get_player(command.player_id)

        if player is None:
            return None

        update = self._movement.stop_with_state(
            player,
            command.state,
            self._elapsed_time,
        )

        if update is None:
            return None

        return PlayerDTO(
            id=update.player_id,
            name=player.name,
            x=int(round(update.position.x)),
            y=int(round(update.position.y)),
            speed=player.current_speed(),
            state=update.state.value,
        )

    def select_target(self, command: SelectTargetCommand) -> PlayerTargetDTO | None:
        """Выбирает или сбрасывает цель игрока и возвращает данные события."""
        player = self._world.get_player(command.player_id)

        if player is None:
            return None

        if command.target is not None and not self._target_exists(command.target):
            return None

        player.selected_target = command.target

        return PlayerTargetDTO(
            id=player.id,
            selected_target=self._target_dto(player.selected_target),
        )

    def _player_dto(self, player: Player) -> PlayerDTO:
        """Преобразует доменного игрока в DTO с целыми координатами."""
        return PlayerDTO(
            id=player.id,
            name=player.name,
            x=int(round(player.position.x)),
            y=int(round(player.position.y)),
            speed=player.current_speed(),
            state=player.state.value,
        )

    def _players_snapshot(
        self,
    ) -> dict[PlayerId, dict[str, float | int | str | dict[str, str] | None]]:
        """Собирает снимок игроков для DTO снимка игрового мира."""
        players = {}

        for player_id, player in self._world.players.items():
            player_data: dict[str, float | int | str | dict[str, str] | None] = (
                player.position.rounded()
            )
            player_data["speed"] = player.current_speed()
            player_data["name"] = player.name
            player_data["state"] = player.state.value
            player_data["selected_target"] = self._target_payload(
                player.selected_target,
            )

            if player.target_position is not None:
                player_data["target_x"] = int(round(player.target_position.x))
                player_data["target_y"] = int(round(player.target_position.y))

            players[player_id] = player_data

        return players

    def _target_exists(self, target: TargetRef) -> bool:
        """Проверяет, существует ли выбранная цель в текущем мире."""
        if target.type == TargetType.PLAYER:
            return self._world.has_player(target.id)

        return False

    def _clear_target_after_movement_started(
        self,
        player_id: PlayerId,
    ) -> PlayerTargetDTO | None:
        """Сбрасывает выбранную цель игрока после успешного старта движения."""
        player = self._world.get_player(player_id)

        if player is None or player.selected_target is None:
            return None

        player.selected_target = None

        return PlayerTargetDTO(
            id=player.id,
            selected_target=None,
        )

    def _target_dto(self, target: TargetRef | None) -> TargetDTO | None:
        """Преобразует доменную ссылку на цель в DTO."""
        if target is None:
            return None

        return TargetDTO(
            type=target.type.value,
            id=target.id,
        )

    def _target_payload(self, target: TargetRef | None) -> dict[str, str] | None:
        """Преобразует выбранную цель в словарь для снимка мира."""
        target_dto = self._target_dto(target)

        if target_dto is None:
            return None

        return {
            "type": target_dto.type,
            "id": target_dto.id,
        }

    def _clear_removed_player_targets(self, player_id: PlayerId) -> None:
        """Сбрасывает ссылки на игрока, который покинул мир."""
        for player in self._world.players.values():
            selected_target = player.selected_target

            if selected_target is None:
                continue

            if (
                selected_target.type == TargetType.PLAYER
                and selected_target.id == player_id
            ):
                player.selected_target = None

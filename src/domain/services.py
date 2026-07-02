from math import hypot

from src.domain.models import (
    CharacterState,
    Player,
    PlayerMovement,
    PlayerUpdate,
    Position,
)


class MovementService:
    """Доменный сервис перемещения игроков."""

    def __init__(
        self,
        speed: int = 100,
        state_change_cooldown_seconds: float = 5.0,
    ) -> None:
        """Создает сервис движения со скоростью игрока по умолчанию."""
        self._speed = speed
        self._state_change_cooldown_seconds = state_change_cooldown_seconds

    def set_target(
        self,
        player: Player,
        target: Position,
        state: CharacterState,
        current_time: float,
    ) -> PlayerMovement | None:
        """Задает игроку целевую точку движения и возвращает событие старта."""
        player.speed = player.speed or self._speed

        if not player.can_transition_to(state, current_time):
            return None

        if self._distance(player.position, target) == 0:
            player.target_position = None
            player.apply_state(
                CharacterState.STANDING,
                current_time,
                self._state_change_cooldown_seconds,
            )
            return None

        player.target_position = target
        player.apply_state(
            state,
            current_time,
            self._state_change_cooldown_seconds,
        )

        return PlayerMovement(
            player_id=player.id,
            position=player.position,
            target=target,
            speed=player.current_speed(),
            state=player.state,
        )

    def tick(self, player: Player, tick_seconds: float) -> PlayerUpdate | None:
        """Сдвигает игрока к цели за один тик и возвращает обновление при достижении."""
        if player.target_position is None:
            return None

        distance = self._distance(player.position, player.target_position)
        step = player.current_speed() * tick_seconds

        if distance <= step:
            player.position = player.target_position
            player.target_position = None
            player.state = CharacterState.STANDING
            return PlayerUpdate(
                player_id=player.id,
                position=player.position,
                state=player.state,
            )

        ratio = step / distance
        player.position.x += (player.target_position.x - player.position.x) * ratio
        player.position.y += (player.target_position.y - player.position.y) * ratio

        return None

    def stop_with_state(
        self,
        player: Player,
        state: CharacterState,
        current_time: float,
    ) -> PlayerUpdate | None:
        """Останавливает игрока в текущей позиции и задает новое состояние."""
        if not player.can_transition_to(state, current_time):
            return None

        player.target_position = None
        player.apply_state(
            state,
            current_time,
            self._state_change_cooldown_seconds,
        )

        return PlayerUpdate(
            player_id=player.id,
            position=player.position,
            state=player.state,
        )

    def _distance(self, current: Position, target: Position) -> float:
        """Считает расстояние между текущей и целевой точками."""
        return hypot(target.x - current.x, target.y - current.y)

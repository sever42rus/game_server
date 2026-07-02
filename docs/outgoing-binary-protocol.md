# Исходящий бинарный протокол

Сервер отправляет клиенту поток бинарных little-endian пакетов. При входе в мир
клиент сначала получает собственный `UUID`, затем серию пакетов создания уже
видимых игроков, а после этого обычные live-обновления.

## Общие правила

- первые `2` байта каждого пакета — это `opcode` (`uint16`, little-endian);
- после `opcode` пакет читается последовательно;
- `UUID` в пакетах передается как бинарное значение длиной `16` байт;
- все состояния, типы и флаги передаются числами;
- новый клиент сначала получает `OWN_PLAYER`, затем набор `PLAYER_SPAWN`, затем
  `SNAPSHOT_END`.

## Коды пакетов

- `0x0201` — `OWN_PLAYER`;
- `0x0202` — `PLAYER_SPAWN`;
- `0x0203` — `SNAPSHOT_END`;
- `0x0204` — `PLAYER_SPAWNED`;
- `0x0205` — `PLAYER_MOVE_STARTED`;
- `0x0206` — `PLAYER_UPDATED`;
- `0x0207` — `PLAYER_TARGET_CHANGED`;
- `0x0208` — `PLAYER_DISCONNECTED`.

## Enum-коды

### Состояние персонажа

- `1` — стоит;
- `2` — идет;
- `3` — бежит;
- `4` — сидит.

### Тип цели

- `1` — игрок.

### Флаги `PLAYER_SPAWN`

- `1` — у игрока выбрана цель;
- `2` — игрок уже движется к целевой точке.

### Флаги `PLAYER_TARGET_CHANGED`

- `1` — после обновления у игрока есть выбранная цель.

## Форматы пакетов

### OWN_PLAYER

Поля:

- `opcode:uint16`;
- `your_id:uuid(16 bytes)`.

Размер пакета: `18` байт.

### PLAYER_SPAWN

Поля:

- `opcode:uint16`;
- `player_id:uuid(16 bytes)`;
- `x:int32`;
- `y:int32`;
- `speed:int32`;
- `state:uint8`;
- `name_length:uint8`;
- `name:utf8[name_length]`;
- `flags:uint8`.

Базовый размер пакета: от `34` до `57` байт.

Дополнительные поля:

- если `flags & 1`, то дальше идут `target_type:uint8` и `target_id:uuid(16 bytes)`;
- если `flags & 2`, то дальше идут `target_x:int32` и `target_y:int32`.

### SNAPSHOT_END

Поля:

- `opcode:uint16`.

Размер пакета: `2` байта.

### PLAYER_SPAWNED

Поля:

- `opcode:uint16`;
- `player_id:uuid(16 bytes)`;
- `x:int32`;
- `y:int32`;
- `speed:int32`;
- `state:uint8`;
- `name_length:uint8`;
- `name:utf8[name_length]`.

Размер пакета: от `33` до `56` байт.

### PLAYER_MOVE_STARTED

Поля:

- `opcode:uint16`;
- `player_id:uuid(16 bytes)`;
- `x:int32`;
- `y:int32`;
- `speed:int32`;
- `state:uint8`;
- `target_x:int32`;
- `target_y:int32`.

Размер пакета: `39` байт.

### PLAYER_UPDATED

Поля:

- `opcode:uint16`;
- `player_id:uuid(16 bytes)`;
- `x:int32`;
- `y:int32`;
- `speed:int32`;
- `state:uint8`.

Размер пакета: `31` байт.

### PLAYER_TARGET_CHANGED

Поля:

- `opcode:uint16`;
- `player_id:uuid(16 bytes)`;
- `flags:uint8`.

Базовый размер пакета: `19` байт.

Если `flags & 1`, то дальше идут:

- `target_type:uint8`;
- `target_id:uuid(16 bytes)`.

### PLAYER_DISCONNECTED

Поля:

- `opcode:uint16`;
- `player_id:uuid(16 bytes)`.

Размер пакета: `18` байт.

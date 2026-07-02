import struct
from uuid import UUID


class PacketReader:
    """Последовательно читает бинарный пакет клиента в формате little-endian."""

    def __init__(self, data: bytes) -> None:
        """Создает reader для указанного бинарного буфера."""
        self._buffer = memoryview(data)
        self._offset = 0

    def remaining(self) -> int:
        """Возвращает количество еще не прочитанных байтов."""
        return len(self._buffer) - self._offset

    def read_bool(self) -> bool:
        """Читает булево значение из одного байта."""
        return self.read_byte() != 0

    def read_byte(self) -> int:
        """Читает один беззнаковый байт."""
        return self._read_unsigned(1)

    def read_short(self) -> int:
        """Читает двухбайтовое беззнаковое целое в little-endian порядке."""
        return self._read_unsigned(2)

    def read_int(self) -> int:
        """Читает четырехбайтовое знаковое целое в little-endian порядке."""
        self._ensure_available(4)
        value = int.from_bytes(
            self._buffer[self._offset : self._offset + 4],
            byteorder="little",
            signed=True,
        )
        self._offset += 4
        return value

    def read_float(self) -> float:
        """Читает четырехбайтовое число с плавающей точкой в little-endian порядке."""
        self._ensure_available(4)
        value = struct.unpack_from("<f", self._buffer, self._offset)[0]
        self._offset += 4
        return value

    def read_uuid(self) -> UUID:
        """Читает UUID из шестнадцати последовательных байтов."""
        raw = self.read_bytes(16)
        return UUID(bytes=raw)

    def read_str(self) -> str:
        """Читает UTF-16LE-строку до нулевого терминатора `0x0000`."""
        chunks = bytearray()

        while True:
            self._ensure_available(2)
            chunk = self.read_bytes(2)

            if chunk == b"\x00\x00":
                return chunks.decode("utf-16-le")

            chunks.extend(chunk)

    def read_bytes(self, length: int) -> bytes:
        """Читает указанное количество байтов без дополнительного преобразования."""
        self._ensure_available(length)
        data = self._buffer[self._offset : self._offset + length].tobytes()
        self._offset += length
        return data

    def _read_unsigned(self, length: int) -> int:
        """Читает беззнаковое целое указанной длины в байтах."""
        self._ensure_available(length)
        value = int.from_bytes(
            self._buffer[self._offset : self._offset + length],
            byteorder="little",
            signed=False,
        )
        self._offset += length
        return value

    def _ensure_available(self, length: int) -> None:
        """Проверяет, что в буфере осталось достаточно байтов для чтения."""
        if length < 0:
            raise ValueError("Packet read length must be non-negative")

        if self.remaining() < length:
            raise ValueError("Packet does not contain enough bytes")


class PacketWriter:
    """Последовательно собирает бинарный пакет клиента в формате little-endian."""

    def __init__(self) -> None:
        """Создает пустой writer для бинарного пакета."""
        self._buffer = bytearray()

    def write_bool(self, value: bool) -> None:
        """Записывает булево значение одним байтом."""
        self.write_byte(1 if value else 0)

    def write_byte(self, value: int) -> None:
        """Записывает один беззнаковый байт."""
        self._buffer.extend(int(value).to_bytes(1, byteorder="little", signed=False))

    def write_short(self, value: int) -> None:
        """Записывает двухбайтовое беззнаковое целое в little-endian порядке."""
        self._buffer.extend(int(value).to_bytes(2, byteorder="little", signed=False))

    def write_int(self, value: int) -> None:
        """Записывает четырехбайтовое знаковое целое в little-endian порядке."""
        self._buffer.extend(int(value).to_bytes(4, byteorder="little", signed=True))

    def write_float(self, value: float) -> None:
        """Записывает четырехбайтовое число с плавающей точкой в little-endian порядке."""
        self._buffer.extend(struct.pack("<f", value))

    def write_uuid(self, value: UUID) -> None:
        """Записывает UUID как шестнадцать последовательных байтов."""
        self._buffer.extend(value.bytes)

    def write_bytes(self, value: bytes) -> None:
        """Записывает последовательность байтов без преобразования."""
        self._buffer.extend(value)

    def write_utf8(self, value: str) -> None:
        """Записывает строку в кодировке UTF-8 без дополнительных префиксов."""
        self._buffer.extend(value.encode("utf-8"))

    def to_bytes(self) -> bytes:
        """Возвращает собранный бинарный пакет."""
        return bytes(self._buffer)

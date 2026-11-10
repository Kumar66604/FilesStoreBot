"""In-memory state for interactive admin commands."""


class BatchState:
    def __init__(self) -> None:
        self._pending: dict[int, dict[str, int | str]] = {}

    def start(self, admin_id: int) -> None:
        self._pending[admin_id] = {"step": "first"}

    def cancel(self, admin_id: int) -> None:
        self._pending.pop(admin_id, None)

    def get(self, admin_id: int) -> dict[str, int | str] | None:
        return self._pending.get(admin_id)

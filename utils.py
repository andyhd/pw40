import asyncio
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import pygame as pg


SceneFn = Callable[[pg.Surface, list[pg.Event], float, dict], "SceneFn | None"]


async def game(
    initial_scene: SceneFn,
    size: tuple[int, int] = (800, 600),
    title: str = "Game",
    *args,
    **kwargs,
):
    pg.init()

    set_mode_kwargs = {
        k: v for k, v in kwargs.items() if k in ("flags", "depth", "display", "vsync")
    }
    screen = pg.display.set_mode(size, **set_mode_kwargs)
    pg.display.set_caption(title)
    clock = pg.time.Clock()
    current_scene = initial_scene
    shared_state = {
        "running": True,
    }

    while shared_state["running"]:
        delta_time = clock.tick(60) / 1000
        events = pg.event.get()

        if any(event.type == pg.QUIT for event in events):
            break

        if next_scene := current_scene(screen, events, delta_time, shared_state):
            current_scene = next_scene

        pg.display.flip()
        await asyncio.sleep(0)


def bind_controls(mapping: dict[str, list[pg.Event]]):

    def get_action(event: pg.Event) -> str | None:
        for action, inputs in mapping.items():
            if any(
                input_
                and event.type == input_.type
                and event.__dict__.items() >= input_.__dict__.items()
                for input_ in inputs
            ):
                return action
        return None

    def map_events_to_actions(events: list[pg.Event]) -> list[str]:
        return [action for event in events if (action := get_action(event))]

    return map_events_to_actions


def asset_loader(path: Path):
    if not path.is_dir():
        raise ValueError(f"Path does not exist: {path}")

    @lru_cache
    def get_asset(name: str):
        matching = path.glob(f"{name}.*")
        try:
            asset_path = next(matching)
        except StopIteration:
            raise LookupError(f"Asset not found: {path / name}")

        if load_fn := {
            **{_: pg.image.load for _ in [".png"]},
            **{_: pg.mixer.Sound for _ in [".ogg"]},
        }.get(asset_path.suffix.lower()):
            return load_fn(asset_path)

        raise ValueError(f"No loader for asset type: {asset_path.suffix}")

    return get_asset


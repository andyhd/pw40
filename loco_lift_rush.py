"""
Loco Lift Rush

You are a lift operator in a busy skyscraper. Your job is to move the
lift up and down to pick up and drop off users as quickly as possible.
Use the arrow keys to control the lift.

A stream of users will call the lift at various floors. You must stop to let
them in and out. The users will get impatient if you take too long, so be
quick!

Controls:
- Up Arrow: Move lift up
- Down Arrow: Move lift down
- Escape: Exit game

Mechanics:
- users continuously arrive to call the lift at random intervals
- users spawn at the left or right (random) side of the screen
- users move horizontally towards the lift
- users board the lift when it arrives at their floor
- users disembark when the lift reaches their destination floor
- The lift cannot move while users are boarding or disembarking
- users have different patience levels

- users move towards the lift when it arrives at their floor
- Building "complete" after a certain number of users served
"""

import asyncio
import random
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from functools import cache

import pygame as pg

from utils import SceneFn, game, bind_controls

WIDTH, HEIGHT = 400, 600
FLOOR_HEIGHT = 50
GROUND = 550
SPAWN_X = [-16, 400]
SPEED_DAMPING = 0.9
MAX_SNAP_SPEED = 50  # max speed to allow snapping to floor
SNAP_THRESHOLD = 10  # pixels from floor to snap

get_actions = bind_controls(
    {
        "pressed_up": pg.Event(pg.KEYDOWN, key=pg.K_UP),
        "released_up": pg.Event(pg.KEYUP, key=pg.K_UP),
        "pressed_down": pg.Event(pg.KEYDOWN, key=pg.K_DOWN),
        "released_down": pg.Event(pg.KEYUP, key=pg.K_DOWN),
        "exit": pg.Event(pg.KEYDOWN, key=pg.K_ESCAPE),
    }
)


class PatienceLevel(Enum):
    """Levels of user patience in seconds."""

    TESTY = 5
    NORMAL = 15
    CHILL = 30


@dataclass
class User:
    """A lift user."""

    floor: int
    """The floor where the user is currently."""
    destination: int
    """The floor where the user wants to go."""
    patience: float
    """How long the user will wait before complaining (in seconds)."""
    rect: pg.FRect | None = None
    """The rectangle representing the user on screen."""
    lift_slot: int | None = None
    """The user's place on the lift."""
    waiting: bool = False
    """Whether the user is waiting for the lift."""
    satisfied: bool = False
    """Whether the user is satisfied (delivered to their destination)."""
    image: pg.Surface | None = None
    """The image representing the user on screen."""


@dataclass
class Lift:
    """A lift."""

    rect: pg.Rect = field(
        default_factory=lambda: pg.Rect(WIDTH // 2 - 25, GROUND - 50, 50, 50))
    """The rectangle representing the lift on screen."""
    velocity: pg.Vector2 = field(default_factory=pg.Vector2)
    """The velocity of the lift."""
    acceleration: pg.Vector2 = field(default_factory=pg.Vector2)
    """The acceleration of the lift."""
    max_speed: float = 300
    """The maximum absolute speed of the lift."""
    min_speed: float = 10 
    """The minimum absolute speed of the lift to be considered moving."""
    passengers: list[User | None] = field(default_factory=list)
    """The users currently on the lift."""
    capacity: int = 4
    """The maximum number of users the lift can hold."""


def users(max_floor: int = 10) -> Generator[User]:
    """
    An infinite generator of users.

    Args:
        max_floor (int): The maximum floor number.
    Yields:
        user
    """
    floors = list(range(max_floor))

    while True:
        floor = random.choice(floors)
        destination = random.choice(list(set(floors) - {floor}))
        patience = random.choice(list(PatienceLevel)).value
        side = random.choice((0, 1))
        rect = pg.FRect(SPAWN_X[side], GROUND - floor * FLOOR_HEIGHT - 30, 16, 30)
        image = pg.Surface((16, 30)).convert_alpha()
        image.fill((0, 0, 0, 0))
        label = pg.Font(None, 20).render(f"{destination:d}", True, "black")
        image.blit(label, (0, 0))
        yield User(floor, destination, patience, rect, image=image)


def play() -> SceneFn:
    lift = Lift()
    lift.passengers = [None] * lift.capacity

    num_floors = 10
    user_stream = users(num_floors)
    avg_arrival_time = 3  # seconds

    state = {
        "time_until_next_user": random.normalvariate(avg_arrival_time),
        "served_users": 0,
        "complaints": 0,
        "all_users": [],
    }

    @cache
    def get_background(screen: pg.Surface) -> pg.Surface:
        bg = pg.Surface(screen.get_size()).convert()
        bg.fill("black")
        floor_rect = pg.Rect(0, 0, WIDTH, FLOOR_HEIGHT)
        for i in range(num_floors):
            c = pg.Color(0x888888).lerp(pg.Color("black"), i / num_floors)
            pg.draw.rect(bg, c, floor_rect.move_to(bottom=GROUND - i * FLOOR_HEIGHT))
            number = pg.Font(None, 20).render(f"{i:d}", True, "white")
            bg.blit(number, (lift.rect.x - 10, GROUND - (i + 1) * FLOOR_HEIGHT + 5))
        pg.draw.rect(bg, "black", (lift.rect.x, 0, lift.rect.width, GROUND))
        return bg

    def _scene(
        screen: pg.Surface,
        events: list[pg.Event],
        delta_time: float,
        shared_state: dict,
    ) -> SceneFn | None:
        screen_rect = screen.get_rect()

        for action in get_actions(events):
            match action:
                case "pressed_up":
                    lift.acceleration.y = -800
                case "pressed_down":
                    lift.acceleration.y = 800

                case "released_up" | "released_down":
                    lift.acceleration.y = 0

                case "exit":
                    return main_menu()

        lift.velocity += lift.acceleration * delta_time
        if abs(lift.velocity.y) < lift.min_speed:
            lift.velocity.y = 0
        if abs(lift.velocity.y) > lift.max_speed:
            lift.velocity.y = lift.max_speed * (1 if lift.velocity.y > 0 else -1)
        lift.velocity *= SPEED_DAMPING
        lift.rect.y += lift.velocity.y * delta_time
        lift.rect.bottom = min(GROUND, lift.rect.bottom)
        lift_floor = (GROUND - lift.rect.bottom) // FLOOR_HEIGHT

        # snap to floors
        if abs(lift.velocity.y) < MAX_SNAP_SPEED:
            offset = (GROUND - lift.rect.bottom) % FLOOR_HEIGHT
            if abs(FLOOR_HEIGHT // 2 - offset) > SNAP_THRESHOLD:
                if offset < FLOOR_HEIGHT // 2:
                    lift.rect.bottom += offset
                else:
                    lift.rect.bottom -= (FLOOR_HEIGHT - offset)

        screen.blit(get_background(screen))
        pg.draw.rect(screen, "grey", lift.rect)

        # spawn new users
        state["time_until_next_user"] -= delta_time
        if state["time_until_next_user"] <= 0:
            new_user = next(user_stream)
            side = int(new_user.rect.centerx < lift.rect.centerx)
            state["all_users"].append(new_user)
            state["time_until_next_user"] = random.normalvariate(avg_arrival_time)

        users_to_remove = []
        for user in state["all_users"]:
            current_floor = (GROUND - user.rect.bottom) // FLOOR_HEIGHT
            destination_floor = GROUND - user.destination * FLOOR_HEIGHT
            at_destination = abs(lift.rect.bottom - destination_floor) < 5

            # user has boarded the lift/is leaving
            if user.lift_slot is not None:

                lift_is_stopped = abs(lift.velocity.y) < 5
                user.satisfied |= at_destination and lift_is_stopped

                if user.satisfied:
                    if lift.passengers[user.lift_slot] is user:
                        lift.passengers[user.lift_slot] = None

                    # move the user off the screen
                    offset = user.rect.centerx - lift.rect.centerx
                    direction = 1 if offset > 0 else -1 if offset < 0 else random.choice((-1, 1))
                    user.rect.x += direction * 50 * delta_time

                else:

                    # ensure the user is on the lift
                    user.rect.bottom = lift.rect.bottom

                    # move to their lift slot
                    slot_width = (lift.rect.width - 16) // lift.capacity
                    slot_x = lift.rect.x + 8 + user.lift_slot * slot_width + slot_width // 2

                    if abs(user.rect.centerx - slot_x) > 1:
                        direction = 1 if user.rect.centerx < slot_x else -1
                        user.rect.x += direction * 50 * delta_time
                    else:
                        user.rect.centerx = slot_x

                # if user has left the screen, update score
                if not screen_rect.contains(user.rect):
                    users_to_remove.append(user)
                    state["served_users"] += 1

            # user is arriving/waiting for the lift
            else:

                # ensure the user is on the floor
                user.rect.bottom = GROUND - current_floor * FLOOR_HEIGHT

                if user.patience:

                    # move towards the lift
                    side = int(user.rect.centerx < lift.rect.centerx)
                    user.rect.x += [-1, 1][side] * 50 * delta_time

                    # # move them to the back of the queue for the side they are on
                    others = [
                        other for other in state["all_users"]
                        if (
                            other.lift_slot is None
                            and other.floor == user.floor
                            and other != user
                            and other.patience > 0
                        )
                    ]
                    if user.rect.centerx < lift.rect.centerx:
                        end_of_queue = min(
                            lift.rect.right,
                            *(
                                other.rect.left for other in others
                                if user.rect.right < other.rect.left < lift.rect.left
                            ),
                            WIDTH,
                        )
                        if end_of_queue <= user.rect.right + 5:
                            user.rect.right = end_of_queue - 5
                            user.waiting = True
                    else:
                        end_of_queue = max(
                            lift.rect.left,
                            *(
                                other.rect.right for other in others
                                if user.rect.left > other.rect.right > lift.rect.right
                            ),
                            0,
                        )
                        if end_of_queue >= user.rect.left - 5:
                            user.rect.left = end_of_queue + 5
                            user.waiting = True

                    # if the lift is not on their floor or full, don't let them board
                    if lift_floor != user.floor or all(lift.passengers):
                        if side:
                            user.rect.right = min(user.rect.right, lift.rect.left - 5)
                        else:
                            user.rect.left = max(user.rect.left, lift.rect.right + 5)
 
                    # board the lift if it is on their floor
                    elif lift.rect.left <= user.rect.centerx <= lift.rect.right:
                        slots = set(range(lift.capacity))
                        occupied = {i for i, p in enumerate(lift.passengers) if p}
                        available = slots - occupied
                        user.lift_slot = random.choice(list(available))
                        user.rect.bottom = lift.rect.bottom
                        lift.passengers[user.lift_slot] = user

                    if user.waiting:
                        user.patience = max(0, user.patience - delta_time)

                else:

                    # user has run out of patience, move off screen
                    direction = -1 if user.rect.centerx < lift.rect.centerx else 1
                    user.rect.x += direction * 100 * delta_time

                    if not screen_rect.contains(user.rect):
                        users_to_remove.append(user)
                        state["complaints"] += 1

            # user color indicates patience level: white -> red
            i = 1 if user.patience > 5 else user.patience / 5
            pg.draw.rect(screen, (255, int(255 * i), int(255 * i)), user.rect) 
            screen.blit(user.image, user.rect)

        while users_to_remove:
            state["all_users"].remove(users_to_remove.pop())

        # draw score
        score = pg.Font(None, 30).render(
            f"Served: {state['served_users']}, Complaints: {state['complaints']}",
            True,
            "white",
        )
        screen.blit(score, (10, 10))

    return _scene


def main_menu() -> SceneFn:
    def _scene(
        screen: pg.Surface,
        events: list[pg.Event],
        delta_time: float,
        shared_state: dict,
    ) -> SceneFn | None:
        if any(event.type == pg.KEYDOWN for event in events):
            return play()

        screen.fill("red")

    return _scene


if __name__ == "__main__":
    asyncio.run(
        game(
            main_menu(),
            size=(WIDTH, HEIGHT),
            title="Loco Lift Rush",
            flags=pg.SCALED | pg.RESIZABLE,
        )
    )

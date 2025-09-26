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
- users have different patience levels
- users who run out of patience leave and count as complaints
- score is based on number of users served and number of complaints
- lift has a maximum capacity
- lift has acceleration and max speed
- lift snaps to floors when moving slowly
- floors are added after a certain number of users are served
-

"""

import random
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

import pygame as pg

from utils import SceneFn, asset_loader, bind_controls

WIDTH, HEIGHT = 800, 800
FLOOR_HEIGHT = 128
SPEED_DAMPING = 0.9
MAX_SNAP_SPEED = 100  # max speed to allow snapping to floor
SNAP_THRESHOLD = 50  # pixels from floor to snap
USER_WIDTH, USER_HEIGHT = 32, FLOOR_HEIGHT
LIFT_WIDTH, LIFT_HEIGHT = 100, FLOOR_HEIGHT
SPAWN_X = [-USER_WIDTH, WIDTH]
USER_SPEED = 100
USER_ANGRY_SPEED = 200
LIFT_ACCELERATION = 1600

get_actions = bind_controls(
    {
        "pressed_up": [pg.Event(pg.KEYDOWN, key=pg.K_UP)],
        "released_up": [pg.Event(pg.KEYUP, key=pg.K_UP)],
        "pressed_down": [pg.Event(pg.KEYDOWN, key=pg.K_DOWN)],
        "released_down": [pg.Event(pg.KEYUP, key=pg.K_DOWN)],
        "mouse_pressed": [pg.Event(pg.MOUSEBUTTONDOWN, button=1)],
        "mouse_released": [pg.Event(pg.MOUSEBUTTONUP, button=1)],
        "exit": [pg.Event(pg.KEYDOWN, key=pg.K_ESCAPE)],
    }
)

assets = asset_loader(Path(__file__).parent / "assets")


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

    rect: pg.Rect = field(default_factory=lambda: pg.Rect(WIDTH // 2 - LIFT_WIDTH // 2, 0, LIFT_WIDTH, LIFT_HEIGHT))
    """The rectangle representing the lift on screen."""
    velocity: pg.Vector2 = field(default_factory=pg.Vector2)
    """The velocity of the lift."""
    acceleration: pg.Vector2 = field(default_factory=pg.Vector2)
    """The acceleration of the lift."""
    max_speed: float = 600
    """The maximum absolute speed of the lift."""
    min_speed: float = 10
    """The minimum absolute speed of the lift to be considered moving."""
    passengers: list[User | None] = field(default_factory=list)
    """The users currently on the lift."""
    capacity: int = 4
    """The maximum number of users the lift can hold."""


def floor_y(i: int, num_floors: int) -> int:
    """
    Get the y-coordinate of the bottom of a floor.
    """
    return (num_floors - i) * FLOOR_HEIGHT


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
        start_floor = random.choice(floors)
        destination = random.choice(list(set(floors) - {start_floor}))
        patience = random.choice(list(PatienceLevel)).value
        side = random.choice((0, 1))
        rect = pg.FRect(SPAWN_X[side], (max_floor - start_floor) * FLOOR_HEIGHT - USER_HEIGHT, USER_WIDTH, USER_HEIGHT)
        image = assets(f"user{random.choice(range(7)):02d}")
        label = pg.Font(None, 30).render(f"{destination:d}", True, "magenta")
        image.blit(label, (0, 0))
        yield User(start_floor, destination, patience, rect, image=image)


@dataclass(kw_only=True)
class GameState:
    all_users: list[User] = field(default_factory=list)
    building_height: int = 0
    camera: pg.FRect = field(default_factory=lambda: pg.FRect(0, 0, WIDTH, HEIGHT))
    complaints: int = 0
    lift_sound: pg.mixer.Sound | None = None
    lift_start_delay: float = 0.0
    num_floors: int = 8
    served_users: int = 0
    time_to_next_user: float = 0.0
    user_stream: Generator[User] | None = None


def play() -> SceneFn:
    avg_arrival_time = 3  # seconds

    state = GameState()
    state.time_to_next_user = random.normalvariate(avg_arrival_time)
    state.user_stream = users(state.num_floors)
    state.building_height = state.num_floors * FLOOR_HEIGHT

    lift = Lift()
    lift.passengers = [None] * lift.capacity
    lift.rect.bottom = state.num_floors * FLOOR_HEIGHT

    arco_font = assets("arco")
    arco_font.set_point_size(50)

    @lru_cache
    def get_background(screen: pg.Surface) -> pg.Surface:
        building_height = state.building_height
        num_floors = state.num_floors
        bg = pg.Surface((WIDTH, building_height + FLOOR_HEIGHT), pg.SRCALPHA)
        bg.fill((0, 0, 0, 0))
        rect = pg.Rect(0, 0, WIDTH, FLOOR_HEIGHT)
        for i in range(num_floors):
            floor_rect = rect.move(0, floor_y(i + 1, num_floors))
            bg.blit(assets(f"floor{random.choice(range(1)):02d}"), floor_rect)
            number = pg.Font(None, 30).render(f"{i:d}", True, "white")
            bg.blit(number, number.get_rect(right=lift.rect.x - 10, top=floor_rect.top + 10))
        return bg

    def _scene(
        screen: pg.Surface,
        events: list[pg.Event],
        delta_time: float,
        shared_state: dict,
    ) -> SceneFn | None:
        screen_rect = screen.get_rect()
        camera = state.camera

        for action in get_actions(events):
            match action:
                case "pressed_up":
                    lift.acceleration.y = -LIFT_ACCELERATION
                case "pressed_down":
                    lift.acceleration.y = LIFT_ACCELERATION

                case "mouse_pressed" if pg.mouse.get_pos()[1] < HEIGHT // 2:
                    lift.acceleration.y = -LIFT_ACCELERATION
                case "mouse_pressed" if pg.mouse.get_pos()[1] >= HEIGHT // 2:
                    lift.acceleration.y = LIFT_ACCELERATION

                case "released_up" | "released_down":
                    lift.acceleration.y = 0

                case "mouse_released":
                    lift.acceleration.y = 0

                case "exit":
                    return main_menu()

        lift_was_stopped = abs(lift.velocity.y) < lift.min_speed

        lift.velocity += lift.acceleration * delta_time
        if abs(lift.velocity.y) < lift.min_speed:
            lift.velocity.y = 0
        if abs(lift.velocity.y) > lift.max_speed:
            lift.velocity.y = lift.max_speed * (1 if lift.velocity.y > 0 else -1)
        lift.velocity *= SPEED_DAMPING
        lift.rect.y += lift.velocity.y * delta_time
        lift.rect.bottom = min(state.building_height, lift.rect.bottom)
        lift.rect.top = max(lift.rect.top, 0)
        lift_floor = (state.building_height - lift.rect.bottom) // FLOOR_HEIGHT

        # snap to floors
        if abs(lift.velocity.y) < MAX_SNAP_SPEED:
            offset = (state.building_height - lift.rect.bottom) % FLOOR_HEIGHT
            if abs(FLOOR_HEIGHT // 2 - offset) > SNAP_THRESHOLD:
                if offset < FLOOR_HEIGHT // 2:
                    lift.rect.bottom += offset
                else:
                    lift.rect.bottom -= (FLOOR_HEIGHT - offset)

        # play lift sounds
        if abs(lift.velocity.y) > 0:

            # starting
            if lift_was_stopped:
                if state.lift_sound:
                    state.lift_sound.stop()
                state.lift_sound = assets("lift_start")
                state.lift_sound.play()
                state.lift_start_delay = state.lift_sound.get_length()

            else:
                # stopping
                if lift.acceleration.y == 0:
                    if state.lift_sound != assets("lift_stop"):
                        if state.lift_sound:
                            state.lift_sound.stop()
                        state.lift_sound = assets("lift_stop")
                        state.lift_sound.play()

                # moving
                elif state.lift_start_delay <= 0:
                    if state.lift_sound != assets("lift_moving"):
                        if state.lift_sound:
                            state.lift_sound.stop()
                        state.lift_sound = assets("lift_moving")
                        state.lift_sound.play(-1)

                # wait until start sound is done
                else:
                    state.lift_start_delay -= delta_time

        # update camera to follow lift
        camera.center = pg.Vector2(camera.center).lerp(lift.rect.center, 0.1)
        camera.bottom = min(camera.bottom, state.num_floors * FLOOR_HEIGHT)

        screen.fill("skyblue")
        screen.blit(
            assets("background"),
            assets("background").get_rect(bottom=HEIGHT - camera.y // 3)
        )
        screen.blit(get_background(screen), (0, 0), area=camera)
        # screen.blit(assets("construction"), (0, -FLOOR_HEIGHT - camera.y))
        screen.blit(assets("lift"), lift.rect.move(0, -camera.top))

        # spawn new users
        state.time_to_next_user -= delta_time
        if state.time_to_next_user <= 0:
            new_user = next(state.user_stream)
            side = int(new_user.rect.centerx < lift.rect.centerx)
            state.all_users.append(new_user)
            state.time_to_next_user = random.normalvariate(avg_arrival_time)

        users_to_remove = []
        for user in state.all_users:
            current_floor = (state.building_height - user.rect.bottom) // FLOOR_HEIGHT
            destination_floor = state.building_height - user.destination * FLOOR_HEIGHT
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
                    user.rect.x += direction * USER_SPEED * delta_time

                else:

                    # ensure the user is on the lift
                    user.rect.bottom = lift.rect.bottom

                    # move to their lift slot
                    slot_width = (lift.rect.width - 16) // lift.capacity
                    slot_x = lift.rect.x + 8 + user.lift_slot * slot_width + slot_width // 2

                    if abs(user.rect.centerx - slot_x) > 1:
                        direction = 1 if user.rect.centerx < slot_x else -1
                        user.rect.x += direction * USER_SPEED * delta_time
                    else:
                        user.rect.centerx = slot_x

                # if user has left the screen, update score
                if not 0 <= user.rect.x <= WIDTH - USER_WIDTH:
                    users_to_remove.append(user)
                    state.served_users += 1

            # user is arriving/waiting for the lift
            else:

                # ensure the user is on the floor
                user.rect.bottom = state.building_height - current_floor * FLOOR_HEIGHT

                if user.patience:

                    # move towards the lift
                    side = int(user.rect.centerx < lift.rect.centerx)
                    user.rect.x += [-1, 1][side] * USER_SPEED * delta_time

                    # # move them to the back of the queue for the side they are on
                    others = [
                        other for other in state.all_users
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
                    user.rect.x += direction * USER_ANGRY_SPEED * delta_time

                    if not screen_rect.contains(user.rect):
                        users_to_remove.append(user)
                        state.complaints += 1

            # user color indicates patience level: white -> red
            i = 1 if user.patience > 5 else user.patience / 5
            # pg.draw.rect(screen, (255, int(255 * i), int(255 * i)), user.rect.move(0, -camera.top))
            screen.blit(user.image, user.rect.move(0, -camera.top))

        while users_to_remove:
            state.all_users.remove(users_to_remove.pop())

        # draw clock
        minutes, seconds = divmod(int(shared_state["time_to_next_level"]), 60)
        shadow = arco_font.render(f"{minutes:02d}:{seconds:02d}", True, "black")
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            screen.blit(shadow, shadow.get_rect(centerx=WIDTH // 2 + dx, top=10 + dy))
        level_time = arco_font.render(f"{minutes:02d}:{seconds:02d}", True, "white")
        screen.blit(level_time, level_time.get_rect(centerx=WIDTH // 2, top=10))

        shared_state["time_to_next_level"] -= delta_time
        if shared_state["time_to_next_level"] <= 0:
            shared_state["served_users"] = state.served_users
            shared_state["complaints"] = state.complaints
            shared_state["num_floors"] = state.num_floors + 1
            get_background.cache_clear()
            return end_level()

        # draw score
        screen.blit(assets("gauge"), assets("gauge").get_rect(bottom=HEIGHT))
        happy = pg.Font(None, 30).render(f"{state.served_users:04d}", True, "white")
        angry = pg.Font(None, 30).render(f"{state.complaints:04d}", True, "white")
        screen.blit(happy, (50, HEIGHT - 80))
        screen.blit(angry, (700, HEIGHT - 80))

    return _scene


def end_level() -> SceneFn:
    def _scene(
        screen: pg.Surface,
        events: list[pg.Event],
        delta_time: float,
        shared_state: dict,
    ) -> SceneFn | None:
        if any(event.type == pg.KEYDOWN and event.key == pg.K_SPACE for event in events):
            shared_state["level_duration"] += 10.0
            shared_state["time_to_next_level"] = shared_state["level_duration"]
            return play()

        screen.fill("blue")
        screen_rect = screen.get_rect()
        text = pg.Font(None, 50).render("Level Complete!", True, "white")
        screen.blit(text, text.get_rect(centerx=screen_rect.centerx, top=100))
        served = shared_state.get("served_users", 0)
        total = served + shared_state.get("complaints", 0)
        if total > 0:
            star_rating = max(0, min(3, (served // total) * 3))
            text = pg.Font(None, 30).render(f"You served {served} / {total} users!", True, "white")
            screen.blit(text, text.get_rect(centerx=screen_rect.centerx, top=200))
            for i in range(3):
                rect = assets("star").get_rect(centerx=screen_rect.centerx - 50 + i * 50, top=300)
                if star_rating >= i + 1:
                    screen.blit(assets("star"), rect)
                else:
                    screen.blit(assets("star_no"), rect)


def main_menu() -> SceneFn:
    def _scene(
        screen: pg.Surface,
        events: list[pg.Event],
        delta_time: float,
        shared_state: dict,
    ) -> SceneFn | None:
        if any(event.type == pg.KEYDOWN for event in events):
            shared_state |= {
                "level_duration": 90.0,
                "time_to_next_level": 90.0,
                "num_floors": 8,
            }
            return play()

        screen.fill("red")

    return _scene

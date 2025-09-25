import asyncio

from loco_lift_rush import HEIGHT, WIDTH, main_menu
from utils import game


asyncio.run(
    game(
        main_menu(),
        size=(WIDTH, HEIGHT),
        title="Loco Lift Rush",
    )
)

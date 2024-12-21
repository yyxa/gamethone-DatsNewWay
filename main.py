import requests
import json
import time
from typing import List, Tuple, Dict

API_URL = 'https://games-test.datsteam.dev/play/snake3d/player/move'
TOKEN = '23d72477-01f2-4137-b526-220ba1ad9e6c'
HEADERS = {
    'X-Auth-Token': TOKEN,
    'Content-Type': 'application/json',
    'Accept-Encoding': 'gzip, deflate'
}

DIRECTIONS = {
    'x_positive': [1, 0, 0],
    'x_negative': [-1, 0, 0],
    'y_positive': [0, 1, 0],
    'y_negative': [0, -1, 0],
    'z_positive': [0, 0, 1],
    'z_negative': [0, 0, -1],
    'no_move': [0, 0, 0] 
}

class Point3D:
    def __init__(self, x: int, y: int, z: int):
        self.x = x
        self.y = y
        self.z = z

    def distance_manhattan(self, other: 'Point3D') -> int:
        return abs(self.x - other.x) + abs(self.y - other.y) + abs(self.z - other.z)

    def to_list(self) -> List[int]:
        return [self.x, self.y, self.z]

    def __eq__(self, other):
        if not isinstance(other, Point3D):
            return False
        return self.x == other.x and self.y == other.y and self.z == other.z

    def __repr__(self):
        return f"Point3D(x={self.x}, y={self.y}, z={self.z})"

class Snake:
    def __init__(self, snake_data: Dict):
        self.id = snake_data['id']
        self.direction = snake_data['direction']
        self.old_direction = snake_data['oldDirection']
        self.geometry = [Point3D(*segment) for segment in snake_data['geometry']]
        self.death_count = snake_data['deathCount']
        self.status = snake_data['status']
        self.revive_remain_ms = snake_data.get('reviveRemainMs', 0)

    def head(self) -> Point3D:
        return self.geometry[0]

class GameState:
    def __init__(self, data: Dict):
        self.map_size = data.get('mapSize', [180, 180, 30])
        self.name = data.get('name', 'Unknown')
        self.points = data.get('points', 0)
        self.fences = [Point3D(*fence) for fence in data.get('fences', [])]
        self.snakes = [Snake(snake) for snake in data.get('snakes', [])]
        self.enemies = data.get('enemies', [])
        self.food = [Point3D(*food['c']) for food in data.get('food', [])]
        self.special_food = data.get('specialFood', {})
        self.turn = data.get('turn', 0)
        self.revive_timeout_sec = data.get('reviveTimeoutSec', 5)
        self.tick_remain_ms = data.get('tickRemainMs', 1000)
        self.errors = data.get('errors', [])

    def get_all_obstacles(self) -> List[Point3D]:
        obstacles = self.fences.copy()
        for snake in self.snakes:
            obstacles.extend(snake.geometry)

        for enemy in self.enemies:
            if enemy['status'] == 'alive':
                obstacles.extend([Point3D(*segment) for segment in enemy['geometry']])
        return obstacles

def get_nearest_food(head: Point3D, food_list: List[Point3D]) -> Point3D:
    if not food_list:
        return None
    nearest = min(food_list, key=lambda f: head.distance_manhattan(f))
    return nearest

def determine_direction(head: Point3D, target: Point3D, obstacles: List[Point3D], map_size: List[int], current_direction: List[int]) -> List[int]:
    if target is None:
        return DIRECTIONS['no_move']

    possible_dirs = [
        DIRECTIONS['x_positive'],
        DIRECTIONS['x_negative'],
        DIRECTIONS['y_positive'],
        DIRECTIONS['y_negative'],
        DIRECTIONS['z_positive'],
        DIRECTIONS['z_negative']
    ]

    opposite_dir = [-current_direction[0], -current_direction[1], -current_direction[2]]
    possible_dirs = [d for d in possible_dirs if d != opposite_dir]

    best_dir = DIRECTIONS['no_move']
    min_distance = float('inf')

    for direction in possible_dirs:
        new_head = Point3D(head.x + direction[0], head.y + direction[1], head.z + direction[2])

        if not (0 <= new_head.x < map_size[0] and 0 <= new_head.y < map_size[1] and 0 <= new_head.z < map_size[2]):
            continue

        if new_head in obstacles:
            continue

        distance = new_head.distance_manhattan(target)
        if distance < min_distance:
            min_distance = distance
            best_dir = direction

    return best_dir

def initialize_snake_id(session: requests.Session) -> str:
    try:
        initial_request = {
            "snakes": []
        }
        response = session.post(API_URL, json=initial_request)
        if response.status_code != 200:
            print(f"Initialization Error: Received status code {response.status_code}")
            print(response.text)
            return None

        game_data = response.json()
        game_state = GameState(game_data)

        if not game_state.snakes:
            print("Initialization Error: No snakes found in the initial response.")
            return None

        my_snake = game_state.snakes[2]
        print(f"Initialized Snake ID: {my_snake.id}")
        return my_snake.id

    except Exception as e:
        print(f"Initialization Exception: {e}")
        return None

def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    snake_id = initialize_snake_id(session)
    if not snake_id:
        print("Failed to initialize snake. Exiting.")
        return

    print("Starting main game loop...")
    while True:
        try:
            move_commands = [{
                "id": snake_id,
                "direction": DIRECTIONS['no_move']
            }]

            request_data = {
                "snakes": move_commands
            }

            response = session.post(API_URL, json=request_data)
            if response.status_code != 200:
                print(f"Error: Received status code {response.status_code}")
                print(response.text)
                time.sleep(1)
                continue

            game_data = response.json()
            game_state = GameState(game_data)

            if not game_state.snakes:
                print("Warning: No active snakes found in the response.")
                time.sleep(1)
                continue

            my_snake = next((s for s in game_state.snakes if s.id == snake_id), None)
            if not my_snake:
                print(f"Warning: Snake with ID {snake_id} not found in the response.")
                time.sleep(1)
                continue

            head = my_snake.head()

            nearest_food = get_nearest_food(head, game_state.food)
            if nearest_food:
                print(f"Nearest food at: {nearest_food}")
            else:
                print("No food available.")

            obstacles = game_state.get_all_obstacles()

            direction = determine_direction(head, nearest_food, obstacles, game_state.map_size, my_snake.direction)
            print(f"Chosen direction: {direction}")

            move_commands = [{
                "id": my_snake.id,
                "direction": direction
            }]

            request_data = {
                "snakes": move_commands
            }

            move_response = session.post(API_URL, json=request_data)
            if move_response.status_code != 200:
                print(f"Error sending move: {move_response.status_code}")
                print(move_response.text)

            time.sleep(1)

        except Exception as e:
            print(f"An exception occurred: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()

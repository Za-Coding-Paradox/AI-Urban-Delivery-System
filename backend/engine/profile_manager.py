# backend/engine/profile_manager.py

import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import jsonschema

from engine.grid_builder import GridBuilder, GridBuilderError

# ── paths ──────────────────────────────────────────────────────────────────────
PROFILES_DIR = Path(__file__).parent.parent / "profiles"
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"
PROFILE_SCHEMA = SCHEMAS_DIR / "city_profile.schema.json"

# ── constants ──────────────────────────────────────────────────────────────────
GRID_WIDTH = 15
GRID_HEIGHT = 15
SCHEMA_VERSION = "1.0"

# Obstacle density range — what fraction of the grid can be obstacles
# Too many obstacles risks making the grid unsolvable
MIN_OBSTACLE_FRACTION = 0.05  # at least  5% obstacles
MAX_OBSTACLE_FRACTION = 0.20  # at most  20% obstacles

# Traffic zone density — fraction of road cells that become traffic zones
TRAFFIC_ZONE_FRACTION = 0.15  # 15% of passable cells become traffic zones


class ProfileManagerError(Exception):
    """Raised when a profile operation fails."""

    pass


class ProfileManager:
    """
    Manages city profiles on disk.

    Responsibilities:
      - list()     → what profiles exist?
      - load()     → give me a specific profile by name
      - save()     → store a profile to disk
      - generate() → create a brand new profile from a seed

    ProfileManager never touches algorithm logic or grid math.
    It only knows about files, names, and the schema contract.
    """

    def __init__(self, profiles_dir: Path = PROFILES_DIR):
        self._profiles_dir = profiles_dir
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._schema = self._load_schema()

    # ── public API ─────────────────────────────────────────────────────────────

    def list(self) -> list[str]:
        """
        Returns the names of all available profiles, without file extensions.
        e.g. ["default_grid", "dense_city", "open_grid"]
        """
        return [p.stem for p in sorted(self._profiles_dir.glob("*.json"))]

    def load(self, name: str) -> dict:
        """
        Loads a profile by name from disk and validates it against the schema.
        Returns the profile dict ready to hand to GridBuilder.

        Raises ProfileManagerError if the file doesn't exist or fails validation.
        """
        path = self._profiles_dir / f"{name}.json"

        if not path.exists():
            available = self.list()
            raise ProfileManagerError(
                f"Profile '{name}' not found. Available profiles: {available}"
            )

        with open(path, "r") as f:
            try:
                profile = json.load(f)
            except json.JSONDecodeError as e:
                raise ProfileManagerError(f"Profile '{name}' contains invalid JSON: {e}")

        self._validate(profile, name)
        return profile

    def save(self, profile: dict, name: str) -> Path:
        """
        Validates and saves a profile dict to disk as {name}.json.
        Returns the path it was saved to.

        Raises ProfileManagerError if validation fails.
        """
        self._validate(profile, name)
        path = self._profiles_dir / f"{name}.json"

        with open(path, "w") as f:
            json.dump(profile, f, indent=2)

        return path

    def generate(self, seed: int, name: Optional[str] = None) -> dict:
        """
        Generates a complete, valid city profile from a seed integer.

        The entire profile is deterministic from the seed — same seed,
        same profile, every time. This is the procedural generation entry point.

        Steps:
          1. Seed a private RNG
          2. Place base station at a random passable position
          3. Scatter obstacles (5–20% of grid)
          4. Convert some road cells to traffic zones
          5. Place 5 delivery points at reachable positions
          6. Validate the result with GridBuilder (connectivity check included)
          7. Return the profile dict (caller decides whether to save it)

        Raises ProfileManagerError if generation fails after max attempts.
        """
        rng = random.Random(seed)
        profile_name = name or f"generated_{seed}"
        max_attempts = 10

        for attempt in range(max_attempts):
            # Use a different sub-seed per attempt so retries aren't identical
            attempt_seed = seed + attempt * 1000
            attempt_rng = random.Random(attempt_seed)

            try:
                profile = self._build_profile(
                    rng=attempt_rng,
                    seed=attempt_seed,
                    name=profile_name,
                )

                # Let GridBuilder run the full validation including connectivity.
                # If it passes, the profile is good.
                GridBuilder().build(profile)
                return profile

            except GridBuilderError:
                # Connectivity failed — retry with a different sub-seed
                # This can happen if obstacles accidentally wall off a destination
                continue

        raise ProfileManagerError(
            f"Could not generate a valid profile from seed {seed} "
            f"after {max_attempts} attempts. "
            f"This is extremely rare — try a different seed."
        )

    # ── generation internals ───────────────────────────────────────────────────

    def _build_profile(self, rng: random.Random, seed: int, name: str) -> dict:
        """
        Builds the raw profile dict from a seeded RNG.
        Does not validate connectivity — that's GridBuilder's job.
        """
        all_positions = [(x, y) for y in range(GRID_HEIGHT) for x in range(GRID_WIDTH)]

        # Shuffle positions using our seeded RNG so selection is deterministic
        rng.shuffle(all_positions)

        # ── place base station ────────────────────────────────────────────────
        # First position after shuffle becomes the base station
        base_x, base_y = all_positions[0]
        reserved = {(base_x, base_y)}

        # ── scatter obstacles ─────────────────────────────────────────────────
        total_cells = GRID_WIDTH * GRID_HEIGHT
        obstacle_count = int(
            rng.uniform(MIN_OBSTACLE_FRACTION, MAX_OBSTACLE_FRACTION) * total_cells
        )

        obstacles = set()
        for pos in all_positions[1:]:
            if len(obstacles) >= obstacle_count:
                break
            if pos not in reserved:
                obstacles.add(pos)
                reserved.add(pos)

        # ── place 5 delivery points ───────────────────────────────────────────
        # Take from the remaining unreserved positions
        delivery_candidates = [p for p in all_positions if p not in reserved]
        delivery_positions = delivery_candidates[:5]

        if len(delivery_positions) < 5:
            raise ProfileManagerError(
                "Not enough passable cells to place 5 delivery points. "
                "Obstacle density is too high."
            )

        delivery_set = set(delivery_positions)
        reserved.update(delivery_set)

        # ── assign traffic zones ──────────────────────────────────────────────
        passable_positions = [p for p in all_positions if p not in obstacles and p not in reserved]
        traffic_count = int(TRAFFIC_ZONE_FRACTION * len(passable_positions))
        traffic_zones = set(passable_positions[:traffic_count])

        # ── build cell list ───────────────────────────────────────────────────
        cells = self._build_cells(
            base=(base_x, base_y),
            obstacles=obstacles,
            traffic_zones=traffic_zones,
            delivery_positions=delivery_positions,
        )

        # ── build delivery sequence ───────────────────────────────────────────
        destinations = [
            {
                "id": f"D{i + 1}",
                "x": x,
                "y": y,
                "label": f"Delivery {i + 1}",
            }
            for i, (x, y) in enumerate(delivery_positions)
        ]

        return {
            "meta": {
                "id": str(uuid.uuid4()),
                "name": name,
                "seed": seed,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": SCHEMA_VERSION,
            },
            "grid": {
                "width": GRID_WIDTH,
                "height": GRID_HEIGHT,
                "cells": cells,
            },
            "robot": {
                "start": {"x": base_x, "y": base_y},
                "movement": "cardinal",
                "cost_model": "edge_cost",
                "tie_breaking": "first",
            },
            "deliveries": {
                "count": 5,
                "destinations": destinations,
                "order": "sequential",
            },
            "algorithms": [
                {
                    "id": "bfs",
                    "enabled": True,
                    "heuristic": "none",
                    "weight": 1.0,
                    "visualize": True,
                },
                {
                    "id": "dfs",
                    "enabled": True,
                    "heuristic": "none",
                    "weight": 1.0,
                    "visualize": True,
                },
                {
                    "id": "ucs",
                    "enabled": True,
                    "heuristic": "none",
                    "weight": 1.0,
                    "visualize": True,
                },
                {
                    "id": "greedy",
                    "enabled": True,
                    "heuristic": "manhattan",
                    "weight": 1.0,
                    "visualize": True,
                },
                {
                    "id": "astar",
                    "enabled": True,
                    "heuristic": "manhattan",
                    "weight": 1.0,
                    "visualize": True,
                },
            ],
        }

    def _build_cells(
        self,
        base: tuple[int, int],
        obstacles: set[tuple[int, int]],
        traffic_zones: set[tuple[int, int]],
        delivery_positions: list[tuple[int, int]],
    ) -> list[dict]:
        """
        Builds the flat Cell[225] list from the sets of special positions.
        Costs are placeholders here — GridBuilder overwrites them with seeded RNG.
        We still need valid placeholder costs so the schema passes.
        """
        delivery_set = set(delivery_positions)
        cells = []

        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                pos = (x, y)

                if pos in obstacles:
                    cell_type = "obstacle"
                    cost = None
                    passable = False
                elif pos == base:
                    cell_type = "base_station"
                    cost = 1
                    passable = True
                elif pos in delivery_set:
                    cell_type = "delivery_point"
                    cost = 1
                    passable = True
                elif pos in traffic_zones:
                    cell_type = "traffic_zone"
                    cost = 10
                    passable = True
                else:
                    cell_type = "road"
                    cost = 1
                    passable = True

                cells.append(
                    {
                        "id": f"{x},{y}",
                        "x": x,
                        "y": y,
                        "type": cell_type,
                        "cost": cost,
                        "passable": passable,
                        "label": None,
                        "metadata": {},
                    }
                )

        return cells

    # ── validation ─────────────────────────────────────────────────────────────

    def _validate(self, profile: dict, name: str) -> None:
        try:
            jsonschema.validate(instance=profile, schema=self._schema)
        except jsonschema.ValidationError as e:
            raise ProfileManagerError(f"Profile '{name}' failed schema validation: {e.message}")

    # ── loader ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_schema() -> dict:
        with open(PROFILE_SCHEMA, "r") as f:
            return json.load(f)

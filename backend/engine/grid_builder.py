# backend/engine/grid_builder.py

import json
import random
from pathlib import Path
from typing import Optional
import jsonschema

# ── paths ──────────────────────────────────────────────────────────────────────
SCHEMAS_DIR  = Path(__file__).parent.parent / "schemas"
REGISTRY_PATH = SCHEMAS_DIR / "cell_type_registry.json"
CELL_SCHEMA_PATH = SCHEMAS_DIR / "cell.schema.json"
PROFILE_SCHEMA_PATH = SCHEMAS_DIR / "city_profile.schema.json"


class GridBuilderError(Exception):
    """Raised when the grid cannot be built from the given profile."""
    pass


class GridBuilder:
    """
    Consumes a CityProfile dict and produces a validated Cell[225] list.

    The builder is intentionally stateful — it holds the RNG instance,
    the loaded registry, and the assembled cells during construction.
    Call build() once per profile. Create a new instance for a new profile.
    """

    def __init__(self):
        self._registry   = self._load_registry()
        self._cell_schema = self._load_schema(CELL_SCHEMA_PATH)
        self._rng: Optional[random.Random] = None
        self._cells: list[dict] = []

    # ── public ──────────────────────────────────────────────────────────────────

    def build(self, profile: dict) -> list[dict]:
        """
        Main entry point. Takes a validated CityProfile dict.
        Returns Cell[225] in row-major order (index = y * 15 + x).

        Raises GridBuilderError on any structural or connectivity problem.
        """
        self._validate_profile_schema(profile)

        seed = profile["meta"]["seed"]
        self._rng = random.Random(seed)

        self._cells = self._build_cells(profile["grid"]["cells"])

        self._validate_passability(profile)
        self._validate_connectivity(profile)

        return self._cells

    # ── cell construction ───────────────────────────────────────────────────────

    def _build_cells(self, raw_cells: list[dict]) -> list[dict]:
        """
        Takes the raw cell list from the profile JSON.
        Assigns costs using the seeded RNG according to the registry cost_range.
        Derives the passable flag from the registry.
        Validates each assembled cell against cell.schema.json.
        """
        built = []

        for raw in raw_cells:
            cell_type = raw["type"]

            if cell_type not in self._registry:
                raise GridBuilderError(
                    f"Cell at ({raw['x']},{raw['y']}) has unknown type '{cell_type}'. "
                    f"Valid types: {list(self._registry.keys())}"
                )

            type_def  = self._registry[cell_type]
            passable  = type_def["passable"]
            cost_range = type_def["cost_range"]

            # Obstacles have no traversal cost — null, not 0
            # Using 0 would imply "free to traverse" which is wrong
            if cost_range is None:
                cost = None
            else:
                cost = self._rng.randint(cost_range[0], cost_range[1])

            cell = {
                "id":       f"{raw['x']},{raw['y']}",
                "x":        raw["x"],
                "y":        raw["y"],
                "type":     cell_type,
                "cost":     cost,
                "passable": passable,
                "label":    raw.get("label", None),
                "metadata": raw.get("metadata", {}),
            }

            # Validate the assembled cell against the schema
            # Catches any mismatch between what we built and what the schema expects
            self._validate_cell(cell)
            built.append(cell)

        # Enforce row-major ordering so index = y * 15 + x is always reliable
        built.sort(key=lambda c: (c["y"], c["x"]))

        if len(built) != 225:
            raise GridBuilderError(
                f"Grid must contain exactly 225 cells (15×15). Got {len(built)}."
            )

        return built

    # ── validation helpers ──────────────────────────────────────────────────────

    def _validate_profile_schema(self, profile: dict) -> None:
        """Validates the full CityProfile dict against city_profile.schema.json."""
        schema = self._load_schema(PROFILE_SCHEMA_PATH)
        try:
            jsonschema.validate(instance=profile, schema=schema)
        except jsonschema.ValidationError as e:
            raise GridBuilderError(f"Profile schema validation failed: {e.message}")

    def _validate_cell(self, cell: dict) -> None:
        """Validates one assembled cell against cell.schema.json."""
        try:
            jsonschema.validate(instance=cell, schema=self._cell_schema)
        except jsonschema.ValidationError as e:
            raise GridBuilderError(
                f"Cell ({cell['x']},{cell['y']}) failed validation: {e.message}"
            )

    def _validate_passability(self, profile: dict) -> None:
        """
        Checks that the base station and all delivery points
        are on passable cells. Fails loudly before any algorithm runs.
        """
        cell_map = self._cell_map()

        start = profile["robot"]["start"]
        start_key = f"{start['x']},{start['y']}"

        if not cell_map[start_key]["passable"]:
            raise GridBuilderError(
                f"Robot start position ({start['x']},{start['y']}) is on an impassable cell."
            )

        for dest in profile["deliveries"]["destinations"]:
            key = f"{dest['x']},{dest['y']}"
            if not cell_map[key]["passable"]:
                raise GridBuilderError(
                    f"Delivery destination '{dest['id']}' at ({dest['x']},{dest['y']}) "
                    f"is on an impassable cell."
                )

    def _validate_connectivity(self, profile: dict) -> None:
        """
        Runs a BFS from the base station to confirm every delivery destination
        is reachable. If any destination is unreachable, raises immediately.

        Why BFS and not DFS?
        BFS is guaranteed to find a path if one exists, regardless of grid shape.
        DFS could theoretically go deep down a dead end and miss a valid path
        in certain edge cases with the termination logic. BFS is the safe choice
        for a simple reachability check.
        """
        cell_map  = self._cell_map()
        start     = profile["robot"]["start"]
        reachable = self._bfs_reachable(start, cell_map)

        for dest in profile["deliveries"]["destinations"]:
            key = f"{dest['x']},{dest['y']}"
            if key not in reachable:
                raise GridBuilderError(
                    f"Delivery destination '{dest['id']}' at ({dest['x']},{dest['y']}) "
                    f"is unreachable from the base station at "
                    f"({start['x']},{start['y']}). Check for obstacle walls."
                )

    # ── BFS reachability ────────────────────────────────────────────────────────

    def _bfs_reachable(self, start: dict, cell_map: dict) -> set[str]:
        """
        Standard BFS from start position.
        Returns the set of cell IDs reachable through passable cells.

        Uses cardinal movement only (4 directions) — matching the assignment spec.
        Even if the profile enables diagonal movement for the robot, reachability
        is checked conservatively with cardinal only. If it's reachable with 4
        directions it's definitely reachable with 8.
        """
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        start_id   = f"{start['x']},{start['y']}"
        visited    = {start_id}
        queue      = [start]

        while queue:
            current = queue.pop(0)
            cx, cy  = current["x"], current["y"]

            for dx, dy in directions:
                nx, ny = cx + dx, cy + dy

                if not (0 <= nx <= 14 and 0 <= ny <= 14):
                    continue

                neighbor_id = f"{nx},{ny}"

                if neighbor_id in visited:
                    continue

                if not cell_map[neighbor_id]["passable"]:
                    continue

                visited.add(neighbor_id)
                queue.append({"x": nx, "y": ny})

        return visited

    # ── utility ─────────────────────────────────────────────────────────────────

    def _cell_map(self) -> dict[str, dict]:
        """Returns a dict keyed by cell ID for O(1) lookup."""
        return {cell["id"]: cell for cell in self._cells}

    # ── loaders ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_registry() -> dict:
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)

    @staticmethod
    def _load_schema(path: Path) -> dict:
        with open(path, "r") as f:
            return json.load(f)

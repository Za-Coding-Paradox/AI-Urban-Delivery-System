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

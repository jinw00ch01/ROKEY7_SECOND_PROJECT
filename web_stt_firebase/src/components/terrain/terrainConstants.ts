export const TERRAIN_SIZE = 24;
export const SEGMENTS = 56;
export const VERTICES_PER_SIDE = SEGMENTS + 1;
export const CURVE_STEPS = 5;
export const MAX_EDGES = SEGMENTS * SEGMENTS * 3;
export const RIBBON_VERTEX_COUNT = MAX_EDGES * CURVE_STEPS * 6;
export const MIN_RIBBON_WIDTH = 0.001;
export const MAX_RIBBON_WIDTH = 0.1;

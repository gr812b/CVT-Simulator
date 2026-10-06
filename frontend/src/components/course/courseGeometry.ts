import type { components } from '@api/generated/backend';
type Point = components['schemas']['CoursePoint'];

/** Convert road arc length to map coordinates without stretching the slope. */
export function projectCourse(points: readonly Point[]) {
  let horizontal = 0;
  return points.map((point, index) => {
    if (index) {
      const ds = point.distance_m - points[index - 1].distance_m;
      const dy = point.elevation_m - points[index - 1].elevation_m;
      horizontal += Math.sqrt(Math.max(0, ds * ds - dy * dy));
    }
    return { ...point, horizontal_m: horizontal };
  });
}

/** Inverse view transform used when dragging a custom section's vertices. */
export function roadFromMap(
  points: readonly { horizontal_m: number; elevation_m: number }[],
): Point[] {
  let distance = 0;
  return points.map((point, index) => {
    if (index)
      distance += Math.hypot(
        point.horizontal_m - points[index - 1].horizontal_m,
        point.elevation_m - points[index - 1].elevation_m,
      );
    return { distance_m: distance, elevation_m: point.elevation_m };
  });
}

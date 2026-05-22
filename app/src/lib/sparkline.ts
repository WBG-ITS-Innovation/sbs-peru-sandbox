// Tiny SVG sparkline path generator. Pure function so it can run in
// both server and client components without a runtime dep.

export interface SparklinePath {
  d: string;       // SVG path data
  width: number;
  height: number;
}

export function sparklinePath(
  values: number[],
  options: { width?: number; height?: number; padding?: number } = {},
): SparklinePath {
  const width = options.width ?? 80;
  const height = options.height ?? 24;
  const padding = options.padding ?? 2;

  if (values.length === 0) {
    return { d: '', width, height };
  }
  if (values.length === 1) {
    const y = height / 2;
    return { d: `M ${padding} ${y} L ${width - padding} ${y}`, width, height };
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const innerW = width - padding * 2;
  const innerH = height - padding * 2;
  const step = innerW / (values.length - 1);

  const points = values.map((v, i) => {
    const x = padding + i * step;
    // Flip y so larger values are higher on screen.
    const y = padding + innerH - ((v - min) / range) * innerH;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return {
    d: `M ${points.join(' L ')}`,
    width,
    height,
  };
}

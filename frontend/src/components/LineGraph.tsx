type LineGraphProps = {
  label: string;
  values: number[];
  min: number;
  max: number;
  unit?: string | null;
};

export function LineGraph({ label, values, min, max, unit }: LineGraphProps) {
  const width = 260;
  const height = 92;
  const points = values
    .slice(-40)
    .map((value, index, list) => {
      const x = list.length <= 1 ? 0 : (index / (list.length - 1)) * width;
      const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
      const y = height - pct * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const latest = values.length ? values[values.length - 1] : null;

  return (
    <section className="graph-panel">
      <div className="status-heading">
        <span>{label}</span>
        <strong>{latest === null ? 'N/A' : `${latest.toFixed(1)}${unit ? ` ${unit}` : ''}`}</strong>
      </div>
      <svg className="line-graph" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label} trend`}>
        <line x1="0" x2={width} y1={height * 0.25} y2={height * 0.25} />
        <line x1="0" x2={width} y1={height * 0.5} y2={height * 0.5} />
        <line x1="0" x2={width} y1={height * 0.75} y2={height * 0.75} />
        {points ? <polyline points={points} /> : <text x="12" y="52">Waiting for data</text>}
      </svg>
    </section>
  );
}

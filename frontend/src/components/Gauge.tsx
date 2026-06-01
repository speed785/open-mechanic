type GaugeProps = {
  label: string;
  value: number | null;
  unit?: string | null;
  min: number;
  max: number;
  warnAt?: number;
};

export function Gauge({ label, value, unit, min, max, warnAt }: GaugeProps) {
  const percent = value === null ? 0 : Math.max(0, Math.min(1, (value - min) / (max - min)));
  const angle = -130 + percent * 260;
  const display = value === null ? 'N/A' : Number.isInteger(value) ? `${value}` : value.toFixed(1);
  const stateClass = warnAt !== undefined && value !== null && value >= warnAt ? 'is-warning' : '';

  return (
    <section className={`gauge-panel ${stateClass}`}>
      <div className="panel-label">{label}</div>
      <svg className="gauge" viewBox="0 0 160 112" role="img" aria-label={`${label} gauge`}>
        <path className="gauge-track" d="M 24 88 A 58 58 0 1 1 136 88" />
        <path
          className="gauge-fill"
          d="M 24 88 A 58 58 0 1 1 136 88"
          pathLength={100}
          style={{ strokeDasharray: `${percent * 100} 100` }}
        />
        <line
          className="gauge-needle"
          x1="80"
          y1="88"
          x2="80"
          y2="40"
          style={{ transform: `rotate(${angle}deg)`, transformOrigin: '80px 88px' }}
        />
        <circle className="gauge-hub" cx="80" cy="88" r="5" />
      </svg>
      <div className="metric-value">
        {display}
        {unit ? <span>{unit}</span> : null}
      </div>
    </section>
  );
}

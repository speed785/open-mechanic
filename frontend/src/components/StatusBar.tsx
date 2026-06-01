type StatusBarProps = {
  label: string;
  value: number | null;
  unit?: string | null;
  min: number;
  max: number;
  neutralMin?: number;
  neutralMax?: number;
};

export function StatusBar({ label, value, unit, min, max, neutralMin, neutralMax }: StatusBarProps) {
  const percent = value === null ? 0 : Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  const outsideNeutral =
    value !== null &&
    neutralMin !== undefined &&
    neutralMax !== undefined &&
    (value < neutralMin || value > neutralMax);
  const display = value === null ? 'N/A' : `${value.toFixed(1)}${unit ? ` ${unit}` : ''}`;

  return (
    <section className="status-panel">
      <div className="status-heading">
        <span>{label}</span>
        <strong className={outsideNeutral ? 'text-warning' : ''}>{display}</strong>
      </div>
      <div className="status-track">
        <div className="status-neutral" />
        <div className="status-marker" style={{ left: `${percent}%` }} />
      </div>
    </section>
  );
}

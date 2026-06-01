import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, DiagnosisResponse, DtcItem, ReportSummary, SensorReading, StatusResponse } from './api';
import { LineGraph } from './components/LineGraph';

type History = Record<string, number[]>;
type SensorGroup = { title: string; names: string[] };

const sensorRanges: Record<string, { min: number; max: number; label: string }> = {
  RPM: { min: 0, max: 7000, label: 'Engine RPM' },
  SPEED: { min: 0, max: 140, label: 'Vehicle Speed' },
  COOLANT_TEMP: { min: 40, max: 125, label: 'Coolant Temp' },
  INTAKE_TEMP: { min: -10, max: 90, label: 'Intake Temp' },
  ENGINE_LOAD: { min: 0, max: 100, label: 'Engine Load' },
  THROTTLE_POS: { min: 0, max: 100, label: 'Throttle' },
  CONTROL_MODULE_VOLTAGE: { min: 10, max: 15.5, label: 'Module Voltage' },
  SHORT_FUEL_TRIM_1: { min: -25, max: 25, label: 'Short Fuel Trim' },
  LONG_FUEL_TRIM_1: { min: -25, max: 25, label: 'Long Fuel Trim' },
  MAF: { min: 0, max: 220, label: 'Mass Air Flow' },
  TIMING_ADVANCE: { min: -20, max: 60, label: 'Timing Advance' },
};

const sensorGroups: SensorGroup[] = [
  { title: 'Powertrain', names: ['RPM', 'SPEED', 'ENGINE_LOAD', 'THROTTLE_POS', 'TIMING_ADVANCE'] },
  { title: 'Thermal', names: ['COOLANT_TEMP', 'INTAKE_TEMP'] },
  { title: 'Electrical', names: ['CONTROL_MODULE_VOLTAGE'] },
  { title: 'Fuel / Air', names: ['SHORT_FUEL_TRIM_1', 'LONG_FUEL_TRIM_1', 'MAF'] },
];

const trendSensors = ['RPM', 'COOLANT_TEMP', 'CONTROL_MODULE_VOLTAGE', 'ENGINE_LOAD'];

export function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [sensors, setSensors] = useState<SensorReading[]>([]);
  const [dtcs, setDtcs] = useState<DtcItem[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResponse | null>(null);
  const [history, setHistory] = useState<History>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);

  const refresh = useCallback(async () => {
    const [nextStatus, nextSensors, nextDtcs, nextReports] = await Promise.all([
      api.status(),
      api.sensors(),
      api.dtcs(),
      api.reports(),
    ]);
    setStatus(nextStatus);
    setSensors(nextSensors.sensors);
    setDtcs(nextDtcs.dtcs);
    setReports(nextReports.reports);
    setHistory((current) => appendHistory(current, nextSensors.sensors));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        await refresh();
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Unable to load dashboard data');
      }
    }
    void load();
    const interval = window.setInterval(load, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [refresh]);

  const sensorMap = useMemo(() => new Map(sensors.map((item) => [item.name, item])), [sensors]);
  const adapter = adapterCopy(status);
  const canDiagnose = Boolean(status?.vehicle_profile && status.vehicle_profile.mileage !== null && status.provider_configured);

  async function connect(offline: boolean) {
    setMessage(offline ? 'Switching to offline mode...' : 'Connecting to adapter...');
    setError(null);
    try {
      const result = await api.connect({ offline });
      setMessage(result.message);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update adapter state');
    }
  }

  async function disconnect() {
    setMessage('Disconnecting adapter...');
    setError(null);
    try {
      const result = await api.disconnect();
      setMessage(result.message);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to disconnect adapter');
    }
  }

  async function runDiagnosis() {
    const profile = status?.vehicle_profile;
    if (!profile || profile.mileage === null) {
      setMessage('Save a vehicle profile with mileage in the terminal tools before running web diagnosis.');
      return;
    }
    setDiagnosing(true);
    setError(null);
    try {
      const result = await api.diagnose({
        vehicle: {
          year: profile.year,
          make: profile.make,
          model: profile.model,
          mileage: profile.mileage,
          vin: profile.vin,
        },
        generated_at: new Date().toISOString(),
      });
      setDiagnosis(result);
      setMessage(result.cached ? 'Diagnosis loaded from cache.' : 'Diagnosis complete.');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to run diagnosis');
    } finally {
      setDiagnosing(false);
    }
  }

  return (
    <main className="app-shell">
      <div className="workspace">
        <header className="command-header">
          <div className="title-block">
            <p className="eyeline">open-mechanic diagnostic run</p>
            <h1>{status?.vehicle_profile?.label ?? 'Unassigned vehicle'}</h1>
            <div className="meta-line">
              <span>v{status?.version ?? '0.1.0'}</span>
              <span>{status?.protocol ?? 'protocol pending'}</span>
              <span>{status?.port ?? 'port auto'}</span>
              <span>Poll: {status?.latest_poll_at ? formatTime(status.latest_poll_at) : 'waiting'}</span>
            </div>
          </div>
          <div className="command-actions" aria-label="Adapter controls">
            <span className={`state-pill state-${status?.adapter_state ?? 'disconnected'}`}>{adapter.label}</span>
            <button type="button" onClick={() => void connect(false)}>Connect</button>
            <button type="button" onClick={() => void connect(true)}>Offline</button>
            <button type="button" onClick={() => void disconnect()}>Disconnect</button>
          </div>
        </header>

        <section className="readiness-grid" aria-label="Runtime readiness">
          <StatusTile label="Adapter" value={adapter.detail} tone={adapter.tone} />
          <StatusTile label="AI Provider" value={status?.provider_name ?? 'checking'} tone={status?.provider_configured ? 'good' : 'warn'} />
          <StatusTile label="Fault Codes" value={dtcs.length ? `${dtcs.length} active` : 'None returned'} tone={dtcs.length ? 'warn' : 'neutral'} />
          <StatusTile label="Reports" value={reports.length ? `${reports.length} saved` : 'No reports'} tone="neutral" />
        </section>

        {message ? <div className="message-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}

        <section className="console-grid">
          <div className="primary-stack">
            <FaultTriage dtcs={dtcs} status={status} />
            <EvidencePanel sensors={sensors} sensorMap={sensorMap} history={history} status={status} />
          </div>
          <aside className="side-stack">
            <DiagnosisPanel
              diagnosis={diagnosis}
              status={status}
              canDiagnose={canDiagnose}
              diagnosing={diagnosing}
              onRun={() => void runDiagnosis()}
            />
            <ReportsPanel reports={reports} />
          </aside>
        </section>
      </div>
    </main>
  );
}

function StatusTile({ label, value, tone }: { label: string; value: string; tone: 'good' | 'warn' | 'neutral' }) {
  return (
    <section className={`status-tile ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function FaultTriage({ dtcs, status }: { dtcs: DtcItem[]; status: StatusResponse | null }) {
  const empty = status?.offline
    ? 'Offline mode: fault codes are not being read from an adapter.'
    : 'No active fault codes returned by the adapter.';
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Fault Triage</h2>
        <span>{dtcs.length ? 'Review active codes first' : 'No code evidence yet'}</span>
      </div>
      <div className="dtc-table">
        {dtcs.length ? (
          dtcs.map((dtc) => (
            <article className="dtc-row" key={dtc.code}>
              <strong>{dtc.code}</strong>
              <span className={`severity severity-${dtc.severity.toLowerCase()}`}>{dtc.severity}</span>
              <span>{dtc.category}</span>
              <span>{dtc.status}</span>
              <p>{dtc.description}</p>
            </article>
          ))
        ) : (
          <div className="empty-row">{empty}</div>
        )}
      </div>
    </section>
  );
}

function EvidencePanel({
  sensors,
  sensorMap,
  history,
  status,
}: {
  sensors: SensorReading[];
  sensorMap: Map<string, SensorReading>;
  history: History;
  status: StatusResponse | null;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Live Evidence</h2>
        <span>{status?.connected ? 'Live adapter data' : status?.offline ? 'Offline mode' : 'Waiting for adapter'}</span>
      </div>
      <div className="sensor-groups">
        {sensorGroups.map((group) => (
          <section className="sensor-group" key={group.title}>
            <h3>{group.title}</h3>
            <div className="sensor-list">
              {group.names.map((name) => (
                <SensorMetric key={name} name={name} reading={sensorMap.get(name)} />
              ))}
            </div>
          </section>
        ))}
      </div>
      <div className="trend-grid">
        {trendSensors.map((name) => {
          const range = sensorRanges[name];
          const reading = sensorMap.get(name);
          return (
            <LineGraph
              key={name}
              label={range.label}
              values={history[name] ?? []}
              min={range.min}
              max={range.max}
              unit={reading?.unit}
            />
          );
        })}
      </div>
      <div className="raw-table">
        <div className="raw-heading">Raw Sensor Values</div>
        {sensors.length ? (
          sensors.map((sensor) => (
            <div className="raw-row" key={sensor.name}>
              <code>{sensor.name}</code>
              <span>{sensor.supported ? `${sensor.value}${sensor.unit ? ` ${sensor.unit}` : ''}` : 'unsupported'}</span>
              <time>{formatTime(sensor.timestamp)}</time>
            </div>
          ))
        ) : (
          <div className="empty-row">No sensor snapshot available.</div>
        )}
      </div>
    </section>
  );
}

function SensorMetric({ name, reading }: { name: string; reading?: SensorReading }) {
  const range = sensorRanges[name];
  const value = reading && reading.supported ? reading.value : 'N/A';
  const unit = reading?.supported ? reading.unit : null;
  return (
    <div className={`sensor-metric ${reading?.supported === false ? 'unsupported' : ''}`}>
      <span>{range?.label ?? name}</span>
      <strong>{value}{unit ? <small> {unit}</small> : null}</strong>
      <em>{reading ? (reading.supported ? 'supported' : 'unsupported') : 'not returned'}</em>
    </div>
  );
}

function DiagnosisPanel({
  diagnosis,
  status,
  canDiagnose,
  diagnosing,
  onRun,
}: {
  diagnosis: DiagnosisResponse | null;
  status: StatusResponse | null;
  canDiagnose: boolean;
  diagnosing: boolean;
  onRun: () => void;
}) {
  const disabledReason = !status?.vehicle_profile
    ? 'Save a vehicle profile in the terminal tools before web diagnosis.'
    : status.vehicle_profile.mileage === null
      ? 'Add mileage to the saved vehicle profile before web diagnosis.'
      : !status.provider_configured
        ? 'Configure an AI provider before running diagnosis.'
        : null;
  return (
    <section className="panel diagnosis-panel">
      <div className="panel-heading">
        <h2>AI Diagnosis</h2>
        <span>{diagnosis?.provider ?? status?.provider_name ?? 'provider pending'}</span>
      </div>
      <button className="primary-action" type="button" disabled={!canDiagnose || diagnosing} onClick={onRun}>
        {diagnosing ? 'Running diagnosis...' : 'Run Diagnosis'}
      </button>
      {disabledReason ? <p className="hint">{disabledReason}</p> : null}
      {diagnosis ? (
        <div className="diagnosis-result">
          <span className={`severity severity-${diagnosis.severity.toLowerCase()}`}>{diagnosis.severity}</span>
          <h3>{diagnosis.summary}</h3>
          <div className="cost-box">
            <span>Estimated cost</span>
            <strong>${diagnosis.estimated_cost_usd.low} - ${diagnosis.estimated_cost_usd.high}</strong>
          </div>
          <DetailList title="Likely Causes" items={diagnosis.likely_causes} />
          <DetailList title="Repair Steps" items={diagnosis.repair_steps} ordered />
          <dl className="diagnosis-meta">
            <div><dt>Urgency</dt><dd>{diagnosis.urgency}</dd></div>
            <div><dt>DIY</dt><dd>{diagnosis.diy_feasible ? diagnosis.diy_difficulty : 'not recommended'}</dd></div>
            <div><dt>Cache</dt><dd>{diagnosis.cached ? 'cached' : 'fresh'}</dd></div>
          </dl>
          <p className="disclaimer">{diagnosis.disclaimer}</p>
        </div>
      ) : (
        <p className="empty-row">Diagnosis output will appear here after a run.</p>
      )}
    </section>
  );
}

function DetailList({ title, items, ordered = false }: { title: string; items: string[]; ordered?: boolean }) {
  if (!items.length) return null;
  const Tag = ordered ? 'ol' : 'ul';
  return (
    <div className="detail-list">
      <h4>{title}</h4>
      <Tag>{items.map((item) => <li key={item}>{item}</li>)}</Tag>
    </div>
  );
}

function ReportsPanel({ reports }: { reports: ReportSummary[] }) {
  return (
    <section className="panel reports-panel">
      <div className="panel-heading">
        <h2>Reports</h2>
        <span>{reports.length ? 'Saved locally' : 'No history yet'}</span>
      </div>
      <div className="report-list">
        {reports.length ? (
          reports.slice(0, 6).map((report) => (
            <article className="report-row" key={report.path}>
              <div>
                <strong>{report.vehicle ?? report.filename}</strong>
                <time>{report.created_at ? formatTime(report.created_at) : 'unknown time'}</time>
              </div>
              <span>{report.severity ?? 'unrated'} / {report.provider ?? 'provider unknown'}</span>
              <p>{report.summary ?? 'No report summary available.'}</p>
              <code>{report.path}</code>
            </article>
          ))
        ) : (
          <p className="empty-row">No saved diagnosis reports yet.</p>
        )}
      </div>
    </section>
  );
}

function adapterCopy(status: StatusResponse | null): { label: string; detail: string; tone: 'good' | 'warn' | 'neutral' } {
  if (!status) return { label: 'Checking', detail: 'Status pending', tone: 'neutral' };
  if (status.adapter_state === 'offline') return { label: 'Offline mode', detail: 'Hardware skipped', tone: 'neutral' };
  if (status.adapter_state === 'connected') return { label: 'Connected', detail: status.protocol ?? 'Adapter online', tone: 'good' };
  if (status.adapter_state === 'error') return { label: 'Adapter error', detail: status.adapter_message ?? 'Connection failed', tone: 'warn' };
  return { label: 'Disconnected', detail: status.adapter_message ?? 'Adapter not connected', tone: 'warn' };
}

function numberValue(reading: SensorReading | undefined): number | null {
  if (!reading || !reading.supported) return null;
  const parsed = Number.parseFloat(reading.value);
  return Number.isFinite(parsed) ? parsed : null;
}

function appendHistory(current: History, readings: SensorReading[]): History {
  if (!readings.length) return current;
  const next: History = { ...current };
  for (const reading of readings) {
    const parsed = numberValue(reading);
    if (parsed === null) continue;
    const previous = next[reading.name] ?? [];
    next[reading.name] = [...previous, parsed].slice(-40);
  }
  return next;
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

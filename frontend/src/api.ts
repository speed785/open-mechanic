export type VehicleProfile = {
  year: number;
  make: string;
  model: string;
  mileage: number | null;
  vin: string | null;
  label: string;
};

export type AdapterState = 'offline' | 'disconnected' | 'connecting' | 'connected' | 'error';

export type StatusResponse = {
  version: string;
  connected: boolean;
  offline: boolean;
  adapter_state: AdapterState;
  adapter_message: string | null;
  port: string | null;
  protocol: string | null;
  provider_name: string;
  provider_configured: boolean;
  vehicle_profile: VehicleProfile | null;
  latest_poll_at: string | null;
};

export type SensorReading = {
  name: string;
  value: string;
  unit: string | null;
  timestamp: string;
  supported: boolean;
};

export type SensorResponse = {
  sensors: SensorReading[];
};

export type DtcItem = {
  code: string;
  description: string;
  status: string;
  severity: string;
  category: string;
};

export type DtcResponse = {
  dtcs: DtcItem[];
};

export type DiagnosisResponse = {
  severity: string;
  summary: string;
  likely_causes: string[];
  repair_steps: string[];
  estimated_cost_usd: { low: number; high: number };
  diy_feasible: boolean;
  diy_difficulty: string;
  urgency: string;
  disclaimer: string;
  dtc_codes: string[];
  vehicle: string;
  provider: string;
  cached: boolean;
};

export type ReportSummary = {
  filename: string;
  path: string;
  created_at: string | null;
  severity: string | null;
  summary: string | null;
  vehicle: string | null;
  provider: string | null;
};

export type ConnectRequest = {
  port?: string | null;
  protocol?: string | null;
  baudrate?: number;
  timeout?: number;
  offline?: boolean;
};

export type VehicleProfileRequest = {
  year: number;
  make: string;
  model: string;
  mileage: number;
  vin?: string | null;
};

export type DiagnosisRequest = {
  vehicle: VehicleProfileRequest;
  generated_at?: string | null;
};

export type MessageResponse = {
  ok: boolean;
  message: string;
};

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const api = {
  status: () => fetchJson<StatusResponse>('/api/status'),
  sensors: () => fetchJson<SensorResponse>('/api/sensors'),
  dtcs: () => fetchJson<DtcResponse>('/api/dtcs'),
  reports: () => fetchJson<{ reports: ReportSummary[] }>('/api/reports'),
  connect: (request: ConnectRequest) =>
    fetchJson<MessageResponse>('/api/connect', {
      method: 'POST',
      body: JSON.stringify(request),
    }),
  disconnect: () => fetchJson<MessageResponse>('/api/disconnect', { method: 'POST' }),
  diagnose: (request: DiagnosisRequest) =>
    fetchJson<DiagnosisResponse>('/api/diagnose', {
      method: 'POST',
      body: JSON.stringify(request),
    }),
};

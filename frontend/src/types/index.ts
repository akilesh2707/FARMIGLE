export interface FarmDetail {
  farm_id: string;
  name: string;
  crop: string;
  language: string;
  area_hectares: number;
}

export interface ZoneResult {
  farm_id: string;
  zone_id: string;
  zone_label?: string;
  ripeness_score?: number;
  status: string;
  health_score?: number;
  health_status: string;
  risk_level: string;
  estimated_harvest_window?: string;
  confidence: number;
  reason_codes: string[];
  recommended_action: string;
  heuristic_version?: string;
}

export interface RiskDetail {
  zone_id: string;
  risk_level: string;
  health_status: string;
  risk_codes: string[];
  confidence: number;
  evidence: any[];
  messages: string[];
}

export interface HealthSummary {
  farm_id: string;
  crop: string;
  crop_stage: string;
  zones_analyzed: number;
  zones_total: number;
  status_counts: Record<string, number>;
  risk_counts: Record<string, number>;
  zones: ZoneResult[];
  risks: RiskDetail[];
  weather?: any;
  satellite?: any;
  is_mock: boolean;
}

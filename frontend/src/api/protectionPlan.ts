import { get } from './request';

export interface PlanItem {
  label: string;
  value: string | boolean;
}

export interface PlanGroup {
  title: string;
  items: PlanItem[];
}

export interface ProtectionPlanData {
  groups: PlanGroup[];
  planText: string;
  updatedAt: string;
}

export function getProtectionPlan() {
  return get<ProtectionPlanData>('/protection-plan');
}

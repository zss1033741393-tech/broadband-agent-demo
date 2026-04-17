export const FAULT_NAME_MAP: Record<string, number> = {
  '频繁WiFi漫游': 1,
  'WiFi干扰严重': 2,
  'WiFi覆盖弱': 3,
  '上行带宽不足': 4,
  'PON口拥塞': 5,
  '多STA竞争': 6,
  'PON光纤中断': 7,
};

export type SimAction =
  | { type: 'start' }
  | { type: 'start_with_fault'; faultName: string; faultId: number }
  | { type: 'inject_fault'; faultName: string; faultId: number }
  | { type: 'unknown_sim_cmd'; raw: string };

export function matchSimCommand(input: string): SimAction | null {
  const trimmed = input.trim();

  // 仿真：启动-<故障名>
  const startWithFaultMatch = trimmed.match(/^仿真[：:]启动[-–—](.+)$/);
  if (startWithFaultMatch) {
    const faultName = startWithFaultMatch[1].trim();
    const faultId = FAULT_NAME_MAP[faultName];
    if (faultId) return { type: 'start_with_fault', faultName, faultId };
    return { type: 'unknown_sim_cmd', raw: trimmed };
  }

  if (/^仿真[：:]启动$/.test(trimmed)) return { type: 'start' };

  const faultMatch = trimmed.match(/^仿真故障[：:](.+)$/);
  if (faultMatch) {
    const faultName = faultMatch[1].trim();
    const faultId = FAULT_NAME_MAP[faultName];
    if (faultId) return { type: 'inject_fault', faultName, faultId };
    return { type: 'unknown_sim_cmd', raw: trimmed };
  }

  if (/^仿真/.test(trimmed)) return { type: 'unknown_sim_cmd', raw: trimmed };
  return null;
}

export const FAULT_NAMES = Object.keys(FAULT_NAME_MAP);

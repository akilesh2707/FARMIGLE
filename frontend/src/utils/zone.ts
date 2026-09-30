export function formatZoneName(zoneId: string, zoneLabel?: string): string {
  if (zoneLabel) {
    return `Zone ${zoneLabel}`;
  }
  return zoneId.replace('zone_', 'Zone ');
}

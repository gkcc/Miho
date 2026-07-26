export const ENDGAME_SAMPLE_STALE_AFTER_DAYS: 15;

export function localDateKey(now?: Date): string;
export function sampleAgeDays(sampleDate: string, today?: string): number | null;
export function staleSampleAgeDays(sampleDate: string, today?: string): number | null;
export function sampleAgeSuffix(sampleDate: string, today?: string): string;
export function nextLocalDateBoundary(now?: Date): number | null;

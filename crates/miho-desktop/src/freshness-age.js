const MILLISECONDS_PER_DAY = 86_400_000;

export const ENDGAME_SAMPLE_STALE_AFTER_DAYS = 15;

function calendarDayNumber(dateKey) {
  if (typeof dateKey !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) return null;
  const [year, month, day] = dateKey.split("-").map(Number);
  if (year < 1) return null;
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);
  if (parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day) return null;
  return parsed.getTime() / MILLISECONDS_PER_DAY;
}

export function localDateKey(now = new Date()) {
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) return "";
  const year = now.getFullYear();
  if (year < 1 || year > 9999) return "";
  return [
    year.toString().padStart(4, "0"),
    (now.getMonth() + 1).toString().padStart(2, "0"),
    now.getDate().toString().padStart(2, "0"),
  ].join("-");
}

export function sampleAgeDays(sampleDate, today = localDateKey()) {
  const sampleDay = calendarDayNumber(sampleDate);
  const todayDay = calendarDayNumber(today);
  return sampleDay === null || todayDay === null ? null : todayDay - sampleDay;
}

export function staleSampleAgeDays(sampleDate, today = localDateKey()) {
  const age = sampleAgeDays(sampleDate, today);
  return age !== null && age >= ENDGAME_SAMPLE_STALE_AFTER_DAYS ? age : null;
}

export function sampleAgeSuffix(sampleDate, today = localDateKey()) {
  const age = sampleAgeDays(sampleDate, today);
  if (age === null) return "";
  if (age < 0) return `（样本日期在 ${-age} 天后）`;
  if (age === 0) return "（今天采样）";
  if (age < ENDGAME_SAMPLE_STALE_AFTER_DAYS) return `（${age} 天前）`;
  return `（已 ${age} 天未更新）`;
}

export function nextLocalDateBoundary(now = new Date()) {
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) return null;
  const boundary = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + 1,
    0,
    0,
    0,
    0,
  ).getTime();
  return Number.isFinite(boundary) && boundary > now.getTime() ? boundary : null;
}

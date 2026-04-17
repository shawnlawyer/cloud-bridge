#!/usr/bin/env node
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';
import {
  ROOM_PASSES,
  buildHeartbeat,
  computeWeeklyCashPressure,
  getNextAction,
  handleUtterance,
  openStewardDb,
} from './steward-core-lib.mjs';

const SCHEMA_VERSION = 'steward-cloudbridge/v1';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const WORKSPACE_ROOT = path.dirname(__dirname);
const DEFAULT_DB_PATH = path.join(WORKSPACE_ROOT, 'state', 'steward.sqlite');
const DEFAULT_TIMEZONE = 'America/New_York';
const DEFAULT_ACTIVE_WINDOW = '08:00-22:00';
const DEFAULT_HEARTBEAT_MINUTES = 30;
const DEFAULT_MORNING_AT = '08:00';
const DEFAULT_MIDDAY_AT = '13:00';
const DEFAULT_EVENING_AT = '21:00';

function parseArgs(argv) {
  const [operation, ...rest] = argv;
  const options = {};
  for (let index = 0; index < rest.length; index += 1) {
    const token = rest[index];
    if (!token.startsWith('--')) {
      continue;
    }
    const key = token.slice(2);
    const next = rest[index + 1];
    if (next == null || next.startsWith('--')) {
      options[key] = true;
      continue;
    }
    options[key] = next;
    index += 1;
  }
  return { operation, options };
}

function isoNow(now = new Date()) {
  return now.toISOString();
}

function scheduleConfig() {
  return {
    timezone: process.env.CLOUD_BRIDGE_STEWARD_TIMEZONE || DEFAULT_TIMEZONE,
    activeWindow: process.env.CLOUD_BRIDGE_STEWARD_ACTIVE_WINDOW || DEFAULT_ACTIVE_WINDOW,
    heartbeatMinutes: Number.parseInt(
      process.env.CLOUD_BRIDGE_STEWARD_HEARTBEAT_MINUTES || String(DEFAULT_HEARTBEAT_MINUTES),
      10,
    ),
    morningAt: process.env.CLOUD_BRIDGE_STEWARD_MORNING_AT || DEFAULT_MORNING_AT,
    middayAt: process.env.CLOUD_BRIDGE_STEWARD_MIDDAY_AT || DEFAULT_MIDDAY_AT,
    eveningAt: process.env.CLOUD_BRIDGE_STEWARD_EVENING_AT || DEFAULT_EVENING_AT,
  };
}

function monthKeyForDate(date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

function zonedParts(now, timezone) {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
  const parts = Object.fromEntries(
    formatter.formatToParts(now).filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]),
  );
  return {
    dateKey: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
    hour: Number.parseInt(parts.hour, 10),
    minute: Number.parseInt(parts.minute, 10),
  };
}

function parseClockTime(value) {
  const match = String(value ?? '').match(/^(\d{2}):(\d{2})$/);
  if (!match) {
    return null;
  }
  return {
    hour: Number.parseInt(match[1], 10),
    minute: Number.parseInt(match[2], 10),
  };
}

function minutesOfDay(parts) {
  return (parts.hour * 60) + parts.minute;
}

function withinActiveWindow(now, config) {
  const parts = zonedParts(now, config.timezone);
  const [startRaw, endRaw] = String(config.activeWindow).split('-');
  const start = parseClockTime(startRaw);
  const end = parseClockTime(endRaw);
  if (!start || !end) {
    return false;
  }
  const current = minutesOfDay(parts);
  const startMinutes = (start.hour * 60) + start.minute;
  const endMinutes = (end.hour * 60) + end.minute;
  return current >= startMinutes && current <= endMinutes;
}

function heartbeatSlot(now, config) {
  const parts = zonedParts(now, config.timezone);
  const interval = Number.isFinite(config.heartbeatMinutes) && config.heartbeatMinutes > 0 ? config.heartbeatMinutes : DEFAULT_HEARTBEAT_MINUTES;
  const roundedMinute = Math.floor(parts.minute / interval) * interval;
  return {
    dateKey: parts.dateKey,
    time: `${String(parts.hour).padStart(2, '0')}:${String(roundedMinute).padStart(2, '0')}`,
  };
}

function sameLocalTime(now, target, timezone) {
  return zonedParts(now, timezone).time === target;
}

function daysInMonth(year, monthIndex) {
  return new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
}

function toUtcDate(year, monthIndex, day) {
  return new Date(Date.UTC(year, monthIndex, day, 12, 0, 0, 0));
}

function calendarDayStamp(date) {
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function daysUntil(date, now) {
  return Math.round((calendarDayStamp(date) - calendarDayStamp(now)) / (24 * 60 * 60 * 1000));
}

function normalizeText(value) {
  return String(value ?? '').trim().replace(/\s+/g, ' ');
}

function titleCase(value) {
  return normalizeText(value)
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function slugify(value) {
  return normalizeText(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function formatCurrency(cents) {
  const value = Number(cents ?? 0) / 100;
  return `$${value.toFixed(2)}`;
}

function makeRef(prefix) {
  return `${prefix}:${Date.now().toString(36)}:${crypto.randomBytes(4).toString('hex')}`;
}

function severityFromNextKind(kind) {
  switch (kind) {
    case 'approval':
    case 'bill':
      return 'attention';
    case 'room':
    case 'task':
      return 'focus';
    default:
      return 'steady';
  }
}

function roomPrompt(roomName, mode, index) {
  if (mode === 'micro') {
    return `Start small in ${titleCase(roomName)}: pick up 3 things.`;
  }
  return `Continue with ${titleCase(roomName)}: ${ROOM_PASSES[index] ?? ROOM_PASSES[ROOM_PASSES.length - 1]}.`;
}

function routineStatus(record, now) {
  if (record.status !== 'active') {
    return {
      state: record.status,
      detail: record.last_done_at ? `Last done ${record.last_done_at.slice(0, 16).replace('T', ' ')}.` : 'Routine is not active.',
    };
  }

  if (record.schedule_type === 'every') {
    const intervalMinutes = Number.parseInt(record.schedule_value, 10);
    if (!Number.isFinite(intervalMinutes)) {
      return { state: 'waiting', detail: 'Schedule is not configured correctly.' };
    }
    const lastDone = record.last_done_at ? new Date(record.last_done_at) : null;
    if (!lastDone) {
      return { state: 'due', detail: `Do this now: ${record.name}.` };
    }
    const elapsedMinutes = Math.floor((now.getTime() - lastDone.getTime()) / (60 * 1000));
    if (elapsedMinutes >= intervalMinutes) {
      return { state: 'due', detail: `Do this now: ${record.name}.` };
    }
    return {
      state: 'waiting',
      detail: `Every ${intervalMinutes}m · last done ${record.last_done_at.slice(0, 16).replace('T', ' ')}.`,
    };
  }

  if (record.schedule_type === 'at') {
    const currentTime = now.toISOString().slice(11, 16);
    const today = now.toISOString().slice(0, 10);
    const lastDoneDay = record.last_done_at ? record.last_done_at.slice(0, 10) : null;
    if (currentTime >= record.schedule_value && lastDoneDay !== today) {
      return { state: 'due', detail: `Do this now: ${record.name}.` };
    }
    return {
      state: 'waiting',
      detail: `At ${record.schedule_value}${lastDoneDay === today ? ' · done today' : ''}.`,
    };
  }

  return { state: 'waiting', detail: 'Routine is queued.' };
}

function nextMonthlyOccurrence(dueDay, now, paidMonthKeys = new Set()) {
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth();
  const currentDueDay = Math.min(dueDay, daysInMonth(year, month));
  const currentOccurrence = toUtcDate(year, month, currentDueDay);
  const currentMonthKey = monthKeyForDate(currentOccurrence);
  if (paidMonthKeys.has(currentMonthKey)) {
    const nextMonthDate = new Date(Date.UTC(year, month + 1, 1, 12, 0, 0, 0));
    const nextYear = nextMonthDate.getUTCFullYear();
    const nextMonth = nextMonthDate.getUTCMonth();
    const nextDueDay = Math.min(dueDay, daysInMonth(nextYear, nextMonth));
    const dueDate = toUtcDate(nextYear, nextMonth, nextDueDay);
    return { dueDate, monthKey: monthKeyForDate(dueDate) };
  }
  return { dueDate: currentOccurrence, monthKey: currentMonthKey };
}

function ensureAdapterSchema(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS approvals (
      id INTEGER PRIMARY KEY,
      approval_ref TEXT NOT NULL UNIQUE,
      title TEXT NOT NULL,
      detail TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      requested_by TEXT NOT NULL DEFAULT 'steward',
      created_at TEXT NOT NULL,
      decided_at TEXT,
      decision TEXT
    );

    CREATE TABLE IF NOT EXISTS notification_events (
      id INTEGER PRIMARY KEY,
      notification_ref TEXT NOT NULL UNIQUE,
      kind TEXT NOT NULL,
      title TEXT NOT NULL,
      detail TEXT,
      severity TEXT NOT NULL DEFAULT 'steady',
      source_ref TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS notification_dismissals (
      id INTEGER PRIMARY KEY,
      notification_ref TEXT NOT NULL UNIQUE,
      dismissed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scheduler_events (
      id INTEGER PRIMARY KEY,
      event_key TEXT NOT NULL UNIQUE,
      mode TEXT NOT NULL,
      emitted_at TEXT NOT NULL
    );
  `);
}

function schedulerEventSeen(db, eventKey) {
  return (db.prepare('SELECT 1 FROM scheduler_events WHERE event_key = ? LIMIT 1').get(eventKey) ?? null) != null;
}

function rememberSchedulerEvent(db, eventKey, mode, now) {
  db.prepare(`
    INSERT INTO scheduler_events (event_key, mode, emitted_at)
    VALUES (?, ?, ?)
    ON CONFLICT (event_key) DO NOTHING
  `).run(eventKey, mode, isoNow(now));
}

function emitScheduledNotification(db, { eventKey, mode, kind, title, detail = null, severity = 'steady', sourceRef = null, now }) {
  if (schedulerEventSeen(db, eventKey)) {
    return false;
  }
  logNotification(db, {
    kind,
    title,
    detail,
    severity,
    sourceRef,
    createdAt: isoNow(now),
  });
  rememberSchedulerEvent(db, eventKey, mode, now);
  return true;
}

function logNotification(db, { kind, title, detail = null, severity = 'steady', sourceRef = null, createdAt = isoNow() }) {
  db.prepare(`
    INSERT INTO notification_events (notification_ref, kind, title, detail, severity, source_ref, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(makeRef('notification'), kind, title, detail, severity, sourceRef, createdAt);
}

function latestState(db) {
  return db.prepare('SELECT * FROM state_events ORDER BY created_at DESC LIMIT 1').get() ?? null;
}

function approvalSummaries(db) {
  const rows = db.prepare('SELECT * FROM approvals ORDER BY CASE WHEN status = \'pending\' THEN 0 ELSE 1 END, created_at DESC').all();
  const pendingRows = rows.filter((row) => row.status === 'pending');
  const summaries = pendingRows.map((row) => ({
    ref: row.approval_ref,
    title: row.title,
    detail: row.detail ?? 'Needs a decision.',
    state: row.status,
    requestedBy: row.requested_by,
    createdAt: row.created_at,
  }));
  return { rows, pendingRows, summaries };
}

function actionDescriptor(action, label, tone = 'primary') {
  return { action, label, tone };
}

function prefixedRef(prefix, value) {
  return `${prefix}:${value}`;
}

function stripRefPrefix(ref, prefix) {
  const normalized = String(ref ?? '').trim();
  const expected = `${prefix}:`;
  if (!normalized.startsWith(expected)) {
    throw new Error(`Expected ${prefix} ref: ${normalized || '(empty)'}`);
  }
  return normalized.slice(expected.length);
}

function dismissedNotificationRefs(db) {
  return new Set(
    db.prepare('SELECT notification_ref FROM notification_dismissals').all().map((row) => row.notification_ref),
  );
}

function billRecords(db, now) {
  const bills = db.prepare('SELECT * FROM bills ORDER BY due_day ASC, name ASC').all();
  const currentMonthKey = monthKeyForDate(now);
  const rows = bills.map((bill) => {
    const paidMonthKeys = new Set(
      db.prepare('SELECT month_key FROM bill_payments WHERE bill_id = ?').all(bill.id).map((row) => row.month_key),
    );
    const nextOccurrence = nextMonthlyOccurrence(Number(bill.due_day), now, paidMonthKeys);
    const paidThisMonth = paidMonthKeys.has(currentMonthKey);
    let state = bill.status;
    if (bill.status === 'active' && !paidThisMonth) {
      if (daysUntil(nextOccurrence.dueDate, now) < 0) {
        state = 'overdue';
      } else if (daysUntil(nextOccurrence.dueDate, now) === 0) {
        state = 'due_today';
      } else if (daysUntil(nextOccurrence.dueDate, now) <= 2) {
        state = 'due_soon';
      } else {
        state = 'upcoming';
      }
    } else if (bill.status === 'active' && paidThisMonth) {
      state = 'paid';
    }
    return {
      id: bill.id,
      ref: prefixedRef('bill', bill.slug),
      slug: bill.slug,
      name: bill.name,
      amountCents: bill.amount_cents,
      amountText: bill.amount_cents == null ? null : formatCurrency(bill.amount_cents),
      dueDay: bill.due_day,
      dueDate: nextOccurrence.dueDate.toISOString().slice(0, 10),
      daysUntil: daysUntil(nextOccurrence.dueDate, now),
      paidThisMonth,
      autopay: Boolean(bill.autopay),
      status: bill.status,
      state,
      actions: [
        ...(!paidThisMonth && bill.status === 'active' ? [actionDescriptor('mark_paid', 'Mark paid')] : []),
        ...(bill.status === 'active' ? [actionDescriptor('pause', 'Pause'), actionDescriptor('remove', 'Remove', 'secondary')] : []),
      ],
      createdAt: bill.created_at,
      updatedAt: bill.updated_at,
    };
  });

  const ordered = [...rows].sort((left, right) => {
    const score = (row) => {
      switch (row.state) {
        case 'overdue':
          return 0;
        case 'due_today':
          return 1;
        case 'due_soon':
          return 2;
        case 'upcoming':
          return 3;
        case 'paid':
          return 4;
        default:
          return 5;
      }
    };
    return score(left) - score(right) || left.daysUntil - right.daysUntil || left.name.localeCompare(right.name);
  });
  const summaries = ordered
    .filter((row) => ['overdue', 'due_today', 'due_soon', 'upcoming'].includes(row.state))
    .slice(0, 8)
    .map((row) => ({
      ref: `bill:${row.slug}`,
      title: row.name,
      detail: `${row.state.replace(/_/g, ' ')} · due ${row.dueDate}${row.amountText ? ` · ${row.amountText}` : ''}`,
      state: row.state,
      dueDate: row.dueDate,
      daysUntil: row.daysUntil,
    }));
  return { summaries, records: ordered };
}

function taskRecords(db) {
  const tasks = db.prepare('SELECT * FROM tasks ORDER BY CASE WHEN status = \'active\' THEN 0 ELSE 1 END, updated_at ASC').all();
  const rows = tasks.map((task) => {
    const steps = db
      .prepare('SELECT step_order, summary, status, completed_at FROM task_steps WHERE task_id = ? ORDER BY step_order ASC')
      .all(task.id)
      .map((step) => ({
        stepOrder: step.step_order,
        summary: step.summary,
        status: step.status,
        completedAt: step.completed_at,
      }));
    const nextStep = steps.find((step) => step.status === 'pending') ?? null;
    const continuity = nextStep ? `Continue with: ${nextStep.summary}.` : task.status === 'done' ? 'Task complete.' : 'No steps queued.';
    const state = task.status === 'active' ? 'focused' : task.status;
    return {
      id: task.id,
      ref: prefixedRef('task', task.slug),
      slug: task.slug,
      label: task.label,
      track: task.track,
      status: task.status,
      state,
      continuity,
      nextStep,
      steps,
      actions: task.status === 'done'
        ? []
        : [actionDescriptor('advance', 'Advance step'), actionDescriptor('complete', 'Complete task', 'secondary')],
      createdAt: task.created_at,
      updatedAt: task.updated_at,
    };
  });
  const summaries = rows.slice(0, 8).map((task) => ({
    ref: `task:${task.slug}`,
    title: task.label,
    detail: task.nextStep ? task.nextStep.summary : task.continuity,
    state: task.state,
    track: task.track,
  }));
  return { summaries, records: rows };
}

function roomRecords(db) {
  const rooms = db.prepare('SELECT * FROM room_sessions ORDER BY CASE WHEN status = \'active\' THEN 0 ELSE 1 END, updated_at DESC').all();
  const rows = rooms.map((room) => {
    const prompt = room.status === 'active'
      ? roomPrompt(room.room_name, room.mode, Number(room.current_index))
      : `Room pass complete: ${room.room_name}.`;
    return {
      id: room.id,
      ref: prefixedRef('room', room.room_slug),
      roomName: room.room_name,
      roomSlug: room.room_slug,
      mode: room.mode,
      currentIndex: room.current_index,
      status: room.status,
      recoveryPrompt: prompt,
      currentPass: room.mode === 'micro' ? 'pick up 3 things' : ROOM_PASSES[Number(room.current_index)] ?? ROOM_PASSES[ROOM_PASSES.length - 1],
      actions: room.status === 'done'
        ? []
        : [actionDescriptor('continue', 'Continue'), actionDescriptor('done', 'Done', 'secondary')],
      createdAt: room.created_at,
      updatedAt: room.updated_at,
    };
  });
  const summaries = rows.slice(0, 6).map((room) => ({
    ref: `room:${room.roomSlug}`,
    title: room.roomName,
    detail: room.recoveryPrompt,
    state: room.status === 'active' ? 'active' : room.status,
    mode: room.mode,
  }));
  return { summaries, records: rows };
}

function routineRecords(db, now) {
  const routines = db.prepare('SELECT * FROM routines ORDER BY CASE WHEN status = \'active\' THEN 0 ELSE 1 END, name ASC').all();
  const rows = routines.map((routine) => {
    const status = routineStatus(routine, now);
    return {
      id: routine.id,
      ref: prefixedRef('routine', routine.slug),
      slug: routine.slug,
      name: routine.name,
      scheduleType: routine.schedule_type,
      scheduleValue: routine.schedule_value,
      lastDoneAt: routine.last_done_at,
      status: routine.status,
      state: status.state,
      detail: status.detail,
      actions: routine.status === 'active' ? [actionDescriptor('mark_done', 'Mark done')] : [],
      createdAt: routine.created_at,
      updatedAt: routine.updated_at,
    };
  });
  const summaries = rows.slice(0, 8).map((routine) => ({
    ref: routine.ref,
    title: routine.name,
    detail: routine.detail,
    state: routine.state,
    scheduleType: routine.scheduleType,
  }));
  return { summaries, records: rows };
}

function importantDateRecords(db, now) {
  const rows = db.prepare('SELECT * FROM important_dates ORDER BY on_date ASC, name ASC').all().map((row) => {
    const eventDate = new Date(`${row.on_date}T12:00:00.000Z`);
    const deltaDays = daysUntil(eventDate, now);
    let state = row.status;
    if (row.status === 'active') {
      if (deltaDays <= 0) {
        state = 'today';
      } else if (deltaDays <= 2) {
        state = 'soon';
      } else {
        state = 'upcoming';
      }
    }
    return {
      id: row.id,
      ref: prefixedRef('important_date', row.slug),
      slug: row.slug,
      name: row.name,
      onDate: row.on_date,
      notes: row.notes,
      status: row.status,
      state,
      daysUntil: deltaDays,
      detail: state === 'today'
        ? `Happening today · ${row.on_date}`
        : state === 'soon'
          ? `Coming up in ${deltaDays} day(s) · ${row.on_date}`
          : `Scheduled for ${row.on_date}`,
      actions: [],
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    };
  });
  const summaries = rows.slice(0, 8).map((row) => ({
    ref: row.ref,
    title: row.name,
    detail: row.detail,
    state: row.state,
    onDate: row.onDate,
  }));
  return { summaries, records: rows };
}

function followupRecords(db, now) {
  const rows = db.prepare('SELECT * FROM followups ORDER BY due_on ASC, label ASC').all().map((row) => {
    const dueDate = new Date(`${row.due_on}T12:00:00.000Z`);
    const deltaDays = daysUntil(dueDate, now);
    let state = row.status;
    if (row.status === 'active') {
      if (deltaDays < 0) {
        state = 'overdue';
      } else if (deltaDays === 0) {
        state = 'today';
      } else if (deltaDays <= 2) {
        state = 'soon';
      } else {
        state = 'upcoming';
      }
    }
    return {
      id: row.id,
      ref: prefixedRef('followup', row.slug),
      slug: row.slug,
      label: row.label,
      dueOn: row.due_on,
      notes: row.notes,
      status: row.status,
      state,
      daysUntil: deltaDays,
      detail: state === 'overdue'
        ? `Overdue follow-up · ${row.due_on}`
        : state === 'today'
          ? `Follow up today · ${row.due_on}`
          : state === 'soon'
            ? `Follow up in ${deltaDays} day(s) · ${row.due_on}`
            : state === 'done'
              ? `Completed${row.completed_at ? ` · ${row.completed_at.slice(0, 10)}` : ''}`
              : `Follow up on ${row.due_on}`,
      completedAt: row.completed_at,
      actions: row.status === 'active' ? [actionDescriptor('mark_done', 'Mark done')] : [],
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    };
  });
  const summaries = rows
    .filter((row) => ['overdue', 'today', 'soon', 'upcoming'].includes(row.state))
    .slice(0, 8)
    .map((row) => ({
      ref: row.ref,
      title: row.label,
      detail: row.detail,
      state: row.state,
      dueOn: row.dueOn,
      daysUntil: row.daysUntil,
    }));
  return { summaries, records: rows };
}

function toolLocationRecords(db) {
  const rows = db.prepare('SELECT * FROM tool_locations ORDER BY noted_at DESC, tool_name ASC').all().map((row) => ({
    id: row.id,
    ref: prefixedRef('tool', row.tool_slug),
    slug: row.tool_slug,
    toolName: row.tool_name,
    location: row.location,
    notedAt: row.noted_at,
    detail: `Last seen in ${row.location}.`,
    actions: [],
  }));
  const summaries = rows.slice(0, 8).map((row) => ({
    ref: row.ref,
    title: row.toolName,
    detail: row.detail,
    state: 'tracked',
    notedAt: row.notedAt,
  }));
  return { summaries, records: rows };
}

function storedNotificationRows(db) {
  return db.prepare('SELECT * FROM notification_events ORDER BY created_at DESC LIMIT 50').all().map((row) => ({
    notificationRef: row.notification_ref,
    kind: row.kind,
    title: row.title,
    detail: row.detail,
    severity: row.severity,
    sourceRef: row.source_ref,
    createdAt: row.created_at,
    derived: false,
  }));
}

function notificationRecords(db, now, oneNextStep = null) {
  const dismissedRefs = dismissedNotificationRefs(db);
  const stored = storedNotificationRows(db);
  const nextAction = oneNextStep;
  const derived = [];
  if (nextAction && nextAction.text !== 'HEARTBEAT_OK') {
    derived.push({
      notificationRef: 'derived:next-step',
      kind: nextAction.kind,
      title: nextAction.text,
      detail: 'Current next step from Steward.',
      severity: severityFromNextKind(nextAction.kind),
      sourceRef: nextAction.approvalRef ?? null,
      createdAt: isoNow(now),
      derived: true,
    });
  }
  const stateEvent = latestState(db);
  if (stateEvent) {
    derived.push({
      notificationRef: `derived:state:${stateEvent.id}`,
      kind: 'state',
      title: `State: ${stateEvent.state}`,
      detail: stateEvent.detail ?? 'Latest recorded state.',
      severity: stateEvent.state === 'overloaded' || stateEvent.state === 'stuck' ? 'attention' : 'steady',
      sourceRef: `state:${stateEvent.id}`,
      createdAt: stateEvent.created_at,
      derived: true,
    });
  }
  const deduped = [];
  const seen = new Set();
  for (const row of [...derived, ...stored]) {
    if (dismissedRefs.has(row.notificationRef)) {
      continue;
    }
    const key = `${row.kind}|${row.title}|${row.detail ?? ''}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(row);
  }
  const summaries = deduped.slice(0, 8).map((row) => ({
    ref: row.notificationRef,
    title: row.title,
    detail: row.detail ?? 'Recent nudge.',
    state: row.severity,
    kind: row.kind,
    createdAt: row.createdAt,
  }));
  return {
    summaries,
    records: deduped.map((row) => ({
      ...row,
      ref: row.notificationRef,
      actions: [actionDescriptor('dismiss', 'Dismiss', 'secondary')],
    })),
  };
}

function approvalRecords(db) {
  const { rows, summaries } = approvalSummaries(db);
  const records = rows.map((row) => ({
    approvalRef: row.approval_ref,
    ref: row.approval_ref,
    title: row.title,
    detail: row.detail,
    status: row.status,
    requestedBy: row.requested_by,
    createdAt: row.created_at,
    decidedAt: row.decided_at,
    decision: row.decision,
    actions: row.status === 'pending'
      ? [actionDescriptor('approve', 'Approve'), actionDescriptor('deny', 'Deny', 'secondary')]
      : [],
  }));
  return { summaries, records };
}

function currentContext(db, now) {
  const activeTask = db.prepare("SELECT * FROM tasks WHERE status = 'active' ORDER BY updated_at ASC LIMIT 1").get() ?? null;
  const activeRoom = db.prepare("SELECT * FROM room_sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1").get() ?? null;
  const stateEvent = latestState(db);
  const cash = computeWeeklyCashPressure(db, now);
  return {
    activeTask: activeTask
      ? {
          label: activeTask.label,
          slug: activeTask.slug,
          track: activeTask.track,
        }
      : null,
    activeRoom: activeRoom
      ? {
          roomName: activeRoom.room_name,
          roomSlug: activeRoom.room_slug,
          mode: activeRoom.mode,
          currentIndex: activeRoom.current_index,
        }
      : null,
    cashPressure: cash,
    latestState: stateEvent
      ? {
          state: stateEvent.state,
          detail: stateEvent.detail,
          source: stateEvent.source,
          createdAt: stateEvent.created_at,
        }
      : null,
  };
}

function todaySnapshot(db, now) {
  const bills = billRecords(db, now).records;
  const tasks = taskRecords(db).records;
  const rooms = roomRecords(db).records;
  const routines = routineRecords(db, now).records;
  const followups = followupRecords(db, now).records;
  const dates = importantDateRecords(db, now).records;
  const approvals = approvalRecords(db).records;
  const notifications = storedNotificationRows(db);
  return {
    overdueBillCount: bills.filter((row) => row.state === 'overdue').length,
    dueSoonBillCount: bills.filter((row) => ['due_today', 'due_soon'].includes(row.state)).length,
    activeTaskCount: tasks.filter((row) => row.status === 'active').length,
    activeRoomCount: rooms.filter((row) => row.status === 'active').length,
    dueRoutineCount: routines.filter((row) => row.state === 'due').length,
    dueFollowupCount: followups.filter((row) => ['overdue', 'today', 'soon'].includes(row.state)).length,
    upcomingDateCount: dates.filter((row) => ['today', 'soon'].includes(row.state)).length,
    pendingApprovalCount: approvals.filter((row) => row.status === 'pending').length,
    notificationCount: notifications.length,
    date: now.toISOString().slice(0, 10),
  };
}

function buildLastWorked(db, now, oneNextStep = null) {
  const latestTask = db.prepare('SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 1').get() ?? null;
  const latestRoom = db.prepare('SELECT * FROM room_sessions ORDER BY updated_at DESC LIMIT 1').get() ?? null;
  const latestNotification = notificationRecords(db, now, oneNextStep).records[0] ?? null;

  const task = latestTask
    ? (() => {
        const nextStep = db
          .prepare('SELECT summary FROM task_steps WHERE task_id = ? AND status = \'pending\' ORDER BY step_order ASC LIMIT 1')
          .get(latestTask.id);
        return {
          ref: prefixedRef('task', latestTask.slug),
          label: latestTask.label,
          status: latestTask.status,
          detail: nextStep?.summary ?? latestTask.track,
          updatedAt: latestTask.updated_at,
        };
      })()
    : null;

  const room = latestRoom
    ? {
        ref: prefixedRef('room', latestRoom.room_slug),
        label: latestRoom.room_name,
        status: latestRoom.status,
        detail: latestRoom.mode === 'micro'
          ? 'pick up 3 things'
          : ROOM_PASSES[Number(latestRoom.current_index)] ?? ROOM_PASSES[ROOM_PASSES.length - 1],
        updatedAt: latestRoom.updated_at,
      }
    : null;

  const notification = latestNotification
    ? {
        ref: latestNotification.notificationRef,
        title: latestNotification.title,
        detail: latestNotification.detail ?? 'Recent notification.',
        kind: latestNotification.kind,
        createdAt: latestNotification.createdAt,
      }
    : null;

  return { task, room, notification };
}

function buildFrontDoor(db, now) {
  const config = scheduleConfig();
  const approvals = approvalRecords(db).records.filter((row) => row.status === 'pending');
  const heartbeat = buildHeartbeat(db, now);
  const stateEvent = latestState(db);
  const oneNextStep = approvals.length > 0
    ? {
        kind: 'approval',
        text: `Decide now: ${approvals[0].title}.`,
        approvalRef: approvals[0].approvalRef,
        detail: approvals[0].detail ?? 'Needs a decision.',
        state: 'pending',
      }
    : (() => {
        const nextAction = getNextAction(db, now);
        return {
          kind: nextAction.kind,
          text: nextAction.text,
          approvalRef: null,
          detail: null,
          state: nextAction.kind === 'steady' ? 'steady' : 'ready',
        };
      })();
  const notificationCount = notificationRecords(db, now, oneNextStep).records.length;
  return {
    schemaVersion: SCHEMA_VERSION,
    operation: 'home',
    title: 'One Next Step',
    state: {
      label: stateEvent?.state ?? (oneNextStep.kind === 'steady' ? 'steady' : 'active'),
      detail: stateEvent?.detail ?? null,
      source: stateEvent?.source ?? 'steward',
    },
    oneNextStep,
    heartbeat,
    currentContext: currentContext(db, now),
    lastWorked: buildLastWorked(db, now, oneNextStep),
    todaySnapshot: {
      ...todaySnapshot(db, now),
      notificationCount,
    },
    schedule: {
      timezone: config.timezone,
      activeWindow: config.activeWindow,
      heartbeatMinutes: config.heartbeatMinutes,
      anchors: {
        morning: config.morningAt,
        midday: config.middayAt,
        evening: config.eveningAt,
      },
    },
  };
}

function recordsPayload(db, kind, now) {
  const normalizedKind = String(kind).toLowerCase();
  let payload;
  switch (normalizedKind) {
    case 'approvals':
      payload = approvalRecords(db);
      break;
    case 'bills':
      payload = billRecords(db, now);
      break;
    case 'routines':
      payload = routineRecords(db, now);
      break;
    case 'followups':
    case 'follow_ups':
    case 'follow-ups':
      payload = followupRecords(db, now);
      break;
    case 'important_dates':
    case 'dates':
      payload = importantDateRecords(db, now);
      break;
    case 'tasks':
      payload = taskRecords(db);
      break;
    case 'rooms':
      payload = roomRecords(db);
      break;
    case 'tool_locations':
    case 'tools':
      payload = toolLocationRecords(db);
      break;
    case 'notification_events':
    case 'notifications':
      payload = notificationRecords(db, now);
      break;
    default:
      throw new Error(`Unsupported records kind: ${kind}`);
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    operation: 'records',
    kind: normalizedKind === 'notifications'
      ? 'notification_events'
      : ['dates', 'important_dates'].includes(normalizedKind)
        ? 'important_dates'
        : ['follow_ups', 'follow-ups'].includes(normalizedKind)
          ? 'followups'
        : ['tool_locations', 'tools'].includes(normalizedKind)
          ? 'tools'
          : normalizedKind,
    summaries: payload.summaries,
    records: payload.records,
  };
}

function ingestPayload(db, text, now) {
  const { action, result } = handleUtterance(db, text, now);
  const frontDoor = buildFrontDoor(db, now);
  if (result.ok && action.type !== 'next_action' && action.type !== 'heartbeat') {
    logNotification(db, {
      kind: result.kind,
      title: result.message,
      detail: `Captured from input: ${text}`,
      severity: severityFromNextKind(frontDoor.oneNextStep.kind),
      sourceRef: action.type,
      createdAt: isoNow(now),
    });
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    operation: 'ingest',
    inputText: text,
    result: {
      ok: result.ok,
      kind: result.kind,
      message: result.message,
      action,
      data: result.data ?? null,
    },
    inferredState: frontDoor.state,
    frontDoor: buildFrontDoor(db, now),
  };
}

function billActionPayload(db, billRef, action, now) {
  const slug = stripRefPrefix(billRef, 'bill');
  const bill = db.prepare('SELECT * FROM bills WHERE slug = ?').get(slug) ?? null;
  if (!bill) {
    throw new Error(`Bill not found: ${billRef}`);
  }

  let result;
  switch (action) {
    case 'mark_paid': {
      const timestamp = isoNow(now);
      const monthKey = monthKeyForDate(now);
      db.prepare(`
        INSERT INTO bill_payments (bill_id, month_key, paid_on, amount_cents)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (bill_id, month_key) DO UPDATE SET
          paid_on = excluded.paid_on,
          amount_cents = excluded.amount_cents
      `).run(bill.id, monthKey, timestamp, bill.amount_cents ?? null);
      db.prepare('UPDATE bills SET updated_at = ? WHERE id = ?').run(timestamp, bill.id);
      result = { ok: true, status: 'paid', title: bill.name, detail: 'Marked paid for the current month.' };
      break;
    }
    case 'pause':
    case 'remove': {
      const status = action === 'pause' ? 'paused' : 'removed';
      db.prepare('UPDATE bills SET status = ?, updated_at = ? WHERE id = ?').run(status, isoNow(now), bill.id);
      result = { ok: true, status, title: bill.name, detail: `${status === 'paused' ? 'Paused' : 'Removed'} bill.` };
      break;
    }
    default:
      throw new Error(`Unsupported bill action: ${action}`);
  }

  return result;
}

function taskActionPayload(db, taskRef, action, now) {
  const slug = stripRefPrefix(taskRef, 'task');
  const task = db.prepare('SELECT * FROM tasks WHERE slug = ?').get(slug) ?? null;
  if (!task) {
    throw new Error(`Task not found: ${taskRef}`);
  }

  if (action === 'complete') {
    db.prepare('UPDATE task_steps SET status = \'done\', completed_at = ? WHERE task_id = ? AND status != \'done\'').run(isoNow(now), task.id);
    db.prepare('UPDATE tasks SET status = \'done\', updated_at = ? WHERE id = ?').run(isoNow(now), task.id);
    return { ok: true, status: 'done', title: task.label, detail: 'Task completed.' };
  }

  if (action !== 'advance') {
    throw new Error(`Unsupported task action: ${action}`);
  }

  const step = db
    .prepare('SELECT * FROM task_steps WHERE task_id = ? AND status = \'pending\' ORDER BY step_order ASC LIMIT 1')
    .get(task.id);
  if (!step) {
    db.prepare('UPDATE tasks SET status = \'done\', updated_at = ? WHERE id = ?').run(isoNow(now), task.id);
    return { ok: true, status: 'done', title: task.label, detail: 'Task already complete.' };
  }

  db.prepare('UPDATE task_steps SET status = \'done\', completed_at = ? WHERE id = ?').run(isoNow(now), step.id);
  const nextStep = db
    .prepare('SELECT * FROM task_steps WHERE task_id = ? AND status = \'pending\' ORDER BY step_order ASC LIMIT 1')
    .get(task.id);
  if (!nextStep) {
    db.prepare('UPDATE tasks SET status = \'done\', updated_at = ? WHERE id = ?').run(isoNow(now), task.id);
    return { ok: true, status: 'done', title: task.label, detail: 'Task completed.' };
  }

  db.prepare('UPDATE tasks SET status = \'active\', updated_at = ? WHERE id = ?').run(isoNow(now), task.id);
  return { ok: true, status: 'active', title: task.label, detail: `Next step: ${nextStep.summary}` };
}

function roomActionPayload(db, roomRef, action, now) {
  const slug = stripRefPrefix(roomRef, 'room');
  const room = db.prepare('SELECT * FROM room_sessions WHERE room_slug = ?').get(slug) ?? null;
  if (!room) {
    throw new Error(`Room not found: ${roomRef}`);
  }

  if (action === 'done') {
    db.prepare('UPDATE room_sessions SET status = \'done\', updated_at = ? WHERE id = ?').run(isoNow(now), room.id);
    return { ok: true, status: 'done', title: room.room_name, detail: 'Room recovery marked done.' };
  }

  if (action !== 'continue') {
    throw new Error(`Unsupported room action: ${action}`);
  }

  if (room.status === 'done') {
    return { ok: true, status: 'done', title: room.room_name, detail: 'Room pass already complete.' };
  }

  const nextIndex = room.mode === 'micro' ? 1 : Number(room.current_index) + 1;
  if (room.mode === 'micro' || nextIndex >= ROOM_PASSES.length) {
    db.prepare('UPDATE room_sessions SET status = \'done\', updated_at = ? WHERE id = ?').run(isoNow(now), room.id);
    return { ok: true, status: 'done', title: room.room_name, detail: 'Room pass complete.' };
  }

  db.prepare('UPDATE room_sessions SET status = \'active\', current_index = ?, updated_at = ? WHERE id = ?').run(nextIndex, isoNow(now), room.id);
  return {
    ok: true,
    status: 'active',
    title: room.room_name,
    detail: roomPrompt(room.room_name, room.mode, nextIndex),
  };
}

function routineActionPayload(db, routineRef, action, now) {
  const slug = stripRefPrefix(routineRef, 'routine');
  const routine = db.prepare('SELECT * FROM routines WHERE slug = ?').get(slug) ?? null;
  if (!routine) {
    throw new Error(`Routine not found: ${routineRef}`);
  }
  if (action !== 'mark_done') {
    throw new Error(`Unsupported routine action: ${action}`);
  }
  db.prepare('UPDATE routines SET last_done_at = ?, updated_at = ? WHERE id = ?').run(
    isoNow(now),
    isoNow(now),
    routine.id,
  );
  return {
    ok: true,
    status: 'done',
    title: routine.name,
    detail: `Marked done: ${routine.name}.`,
  };
}

function followupActionPayload(db, followupRef, action, now) {
  const slug = stripRefPrefix(followupRef, 'followup');
  const followup = db.prepare('SELECT * FROM followups WHERE slug = ?').get(slug) ?? null;
  if (!followup) {
    throw new Error(`Follow-up not found: ${followupRef}`);
  }
  if (action !== 'mark_done') {
    throw new Error(`Unsupported follow-up action: ${action}`);
  }
  db.prepare('UPDATE followups SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?').run(
    'done',
    isoNow(now),
    isoNow(now),
    followup.id,
  );
  return {
    ok: true,
    status: 'done',
    title: followup.label,
    detail: `Marked done: ${followup.label}.`,
  };
}

function notificationActionPayload(db, notificationRef, action, now) {
  if (action !== 'dismiss') {
    throw new Error(`Unsupported notification action: ${action}`);
  }

  db.prepare(`
    INSERT INTO notification_dismissals (notification_ref, dismissed_at)
    VALUES (?, ?)
    ON CONFLICT (notification_ref) DO UPDATE SET dismissed_at = excluded.dismissed_at
  `).run(notificationRef, isoNow(now));

  return {
    ok: true,
    status: 'dismissed',
    title: notificationRef,
    detail: 'Notification dismissed.',
  };
}

function billReminderMessage(record) {
  switch (record.state) {
    case 'overdue':
      return `Handle this first: ${record.name} is overdue.`;
    case 'due_today':
      return `Handle this first: ${record.name} is due today.`;
    case 'due_soon':
      return `Plan this now: ${record.name} is due in ${record.daysUntil} day(s).`;
    default:
      return null;
  }
}

function importantDateReminderMessage(record) {
  switch (record.state) {
    case 'today':
      return `Handle this first: ${record.name} is today.`;
    case 'soon':
      return `Prepare now: ${record.name} is in ${record.daysUntil} day(s).`;
    default:
      return null;
  }
}

function followupReminderMessage(record) {
  switch (record.state) {
    case 'overdue':
    case 'today':
      return `Follow up now: ${record.label}.`;
    case 'soon':
      return `Plan follow-up: ${record.label} is in ${record.daysUntil} day(s).`;
    default:
      return null;
  }
}

function activeTaskPrompt(db) {
  const activeTask = db.prepare("SELECT * FROM tasks WHERE status = 'active' ORDER BY updated_at ASC LIMIT 1").get() ?? null;
  if (!activeTask) {
    return null;
  }
  const step = db
    .prepare('SELECT summary FROM task_steps WHERE task_id = ? AND status = \'pending\' ORDER BY step_order ASC LIMIT 1')
    .get(activeTask.id);
  return step?.summary ? `Continue with: ${step.summary}.` : `Continue with: ${activeTask.label}.`;
}

function tickHeartbeat(db, now, config) {
  if (!withinActiveWindow(now, config)) {
    return { mode: 'heartbeat', status: 'skipped', message: 'Outside active window.' };
  }
  const nextAction = getNextAction(db, now);
  if (nextAction.text === 'HEARTBEAT_OK') {
    return { mode: 'heartbeat', status: 'noop', message: 'HEARTBEAT_OK' };
  }
  const slot = heartbeatSlot(now, config);
  const eventKey = `heartbeat:${slot.dateKey}:${slot.time}`;
  const emitted = emitScheduledNotification(db, {
    eventKey,
    mode: 'heartbeat',
    kind: nextAction.kind,
    title: nextAction.text,
    detail: 'Heartbeat nudge.',
    severity: severityFromNextKind(nextAction.kind),
    sourceRef: 'heartbeat',
    now,
  });
  return {
    mode: 'heartbeat',
    status: emitted ? 'emitted' : 'noop',
    message: nextAction.text,
    eventKey,
  };
}

function tickAnchor(db, now, config, mode) {
  const target = mode === 'morning' ? config.morningAt : mode === 'midday' ? config.middayAt : config.eveningAt;
  if (!sameLocalTime(now, target, config.timezone)) {
    return { mode, status: 'skipped', message: `Not ${mode} anchor time.` };
  }
  const parts = zonedParts(now, config.timezone);
  const eventKey = `anchor:${mode}:${parts.dateKey}`;
  const nextAction = getNextAction(db, now);
  const taskPrompt = activeTaskPrompt(db);
  const title = mode === 'morning'
    ? (nextAction.text === 'HEARTBEAT_OK' ? 'Morning check-in: pick one thing that matters.' : nextAction.text)
    : mode === 'midday'
      ? (taskPrompt ?? (nextAction.text === 'HEARTBEAT_OK' ? 'Midday drift check: pick one thing and move it.' : nextAction.text))
      : (taskPrompt ? `Evening closeout: ${taskPrompt}` : 'Evening closeout: mark what is done and park the next step.');
  const kind = mode === 'evening' ? 'anchor' : (nextAction.kind === 'steady' ? 'anchor' : nextAction.kind);
  const emitted = emitScheduledNotification(db, {
    eventKey,
    mode,
    kind,
    title,
    detail: 'Scheduled anchor.',
    severity: severityFromNextKind(kind),
    sourceRef: mode,
    now,
  });
  return { mode, status: emitted ? 'emitted' : 'noop', message: title, eventKey };
}

function tickBills(db, now, config) {
  const parts = zonedParts(now, config.timezone);
  const eventKey = `bills:${parts.dateKey}`;
  const bill = billRecords(db, now).records.find((row) => ['overdue', 'due_today', 'due_soon'].includes(row.state)) ?? null;
  const message = bill ? billReminderMessage(bill) : 'No bill reminder due.';
  if (!bill || !message) {
    return { mode: 'bills', status: 'noop', message };
  }
  const emitted = emitScheduledNotification(db, {
    eventKey,
    mode: 'bills',
    kind: 'bill',
    title: message,
    detail: `${bill.name} · ${bill.dueDate}${bill.amountText ? ` · ${bill.amountText}` : ''}`,
    severity: severityFromNextKind('bill'),
    sourceRef: bill.ref,
    now,
  });
  return { mode: 'bills', status: emitted ? 'emitted' : 'noop', message, eventKey };
}

function tickDates(db, now, config) {
  const parts = zonedParts(now, config.timezone);
  const eventKey = `dates:${parts.dateKey}`;
  const dateRow = importantDateRecords(db, now).records.find((row) => ['today', 'soon'].includes(row.state)) ?? null;
  const message = dateRow ? importantDateReminderMessage(dateRow) : 'No date reminder due.';
  if (!dateRow || !message) {
    return { mode: 'dates', status: 'noop', message };
  }
  const emitted = emitScheduledNotification(db, {
    eventKey,
    mode: 'dates',
    kind: 'important_date',
    title: message,
    detail: `${dateRow.name} · ${dateRow.onDate}`,
    severity: severityFromNextKind('task'),
    sourceRef: dateRow.ref,
    now,
  });
  return { mode: 'dates', status: emitted ? 'emitted' : 'noop', message, eventKey };
}

function tickFollowups(db, now, config) {
  const parts = zonedParts(now, config.timezone);
  const eventKey = `followups:${parts.dateKey}`;
  const row = followupRecords(db, now).records.find((item) => ['overdue', 'today', 'soon'].includes(item.state)) ?? null;
  const message = row ? followupReminderMessage(row) : 'No follow-up reminder due.';
  if (!row || !message) {
    return { mode: 'followups', status: 'noop', message };
  }
  const emitted = emitScheduledNotification(db, {
    eventKey,
    mode: 'followups',
    kind: 'followup',
    title: message,
    detail: `${row.label} · ${row.dueOn}`,
    severity: severityFromNextKind('task'),
    sourceRef: row.ref,
    now,
  });
  return { mode: 'followups', status: emitted ? 'emitted' : 'noop', message, eventKey };
}

function tickPayload(db, mode, now) {
  const config = scheduleConfig();
  const normalizedMode = String(mode || 'all').toLowerCase();
  const sequence = normalizedMode === 'all'
    ? ['heartbeat', 'morning', 'midday', 'evening', 'bills', 'followups', 'dates']
    : [normalizedMode];
  const runs = [];
  for (const entry of sequence) {
    switch (entry) {
      case 'heartbeat':
        runs.push(tickHeartbeat(db, now, config));
        break;
      case 'morning':
      case 'midday':
      case 'evening':
        runs.push(tickAnchor(db, now, config, entry));
        break;
      case 'bills':
        runs.push(tickBills(db, now, config));
        break;
      case 'followups':
        runs.push(tickFollowups(db, now, config));
        break;
      case 'dates':
        runs.push(tickDates(db, now, config));
        break;
      default:
        throw new Error(`Unsupported tick mode: ${mode}`);
    }
  }
  const emittedCount = runs.filter((run) => run.status === 'emitted').length;
  return {
    schemaVersion: SCHEMA_VERSION,
    operation: 'tick',
    mode: normalizedMode,
    result: {
      status: emittedCount > 0 ? 'emitted' : 'noop',
      emittedCount,
      runs,
    },
    frontDoor: buildFrontDoor(db, now),
  };
}

function approvalDecisionPayload(db, approvalRef, decision, now) {
  if (!['approve', 'deny'].includes(decision)) {
    throw new Error('decision must be approve or deny');
  }
  const approval = db.prepare('SELECT * FROM approvals WHERE approval_ref = ?').get(approvalRef) ?? null;
  if (!approval) {
    throw new Error(`Approval not found: ${approvalRef}`);
  }
  const nextStatus = decision === 'approve' ? 'approved' : 'denied';
  db.prepare('UPDATE approvals SET status = ?, decision = ?, decided_at = ? WHERE approval_ref = ?').run(
    nextStatus,
    decision,
    isoNow(now),
    approvalRef,
  );
  logNotification(db, {
    kind: 'approval',
    title: `${decision === 'approve' ? 'Approved' : 'Denied'}: ${approval.title}`,
    detail: approval.detail ?? 'Approval resolved.',
    severity: decision === 'approve' ? 'steady' : 'attention',
    sourceRef: approvalRef,
    createdAt: isoNow(now),
  });
  return {
    schemaVersion: SCHEMA_VERSION,
    operation: 'approval',
    decision,
    approvalRef,
    result: {
      ok: true,
      status: nextStatus,
      title: approval.title,
      detail: approval.detail,
    },
    frontDoor: buildFrontDoor(db, now),
  };
}

function actionPayload(db, kind, ref, action, now) {
  const normalizedKind = String(kind).toLowerCase();
  let result;
  let outputKind = normalizedKind;
  switch (normalizedKind) {
    case 'approvals':
      result = approvalDecisionPayload(db, ref, action, now).result;
      break;
    case 'bills':
      result = billActionPayload(db, ref, action, now);
      break;
    case 'routines':
      result = routineActionPayload(db, ref, action, now);
      break;
    case 'followups':
      result = followupActionPayload(db, ref, action, now);
      break;
    case 'tasks':
      result = taskActionPayload(db, ref, action, now);
      break;
    case 'rooms':
      result = roomActionPayload(db, ref, action, now);
      break;
    case 'notification_events':
    case 'notifications':
      outputKind = 'notification_events';
      result = notificationActionPayload(db, ref, action, now);
      break;
    default:
      throw new Error(`Unsupported action kind: ${kind}`);
  }

  const lane = recordsPayload(db, outputKind, now);

  return {
    schemaVersion: SCHEMA_VERSION,
    operation: 'action',
    kind: outputKind,
    ref,
    action,
    result,
    records: lane.records,
    summaries: lane.summaries,
    frontDoor: buildFrontDoor(db, now),
  };
}

function openDb(dbPath) {
  const db = openStewardDb(dbPath);
  ensureAdapterSchema(db);
  return db;
}

function main() {
  const { operation, options } = parseArgs(process.argv.slice(2));
  if (!operation) {
    throw new Error('operation is required');
  }
  const dbPath = options.db ? path.resolve(options.db) : path.resolve(process.env.CLOUD_BRIDGE_STEWARD_DB_PATH ?? DEFAULT_DB_PATH);
  const now = options.now ? new Date(options.now) : new Date();
  if (Number.isNaN(now.getTime())) {
    throw new Error(`invalid --now value: ${options.now}`);
  }
  const db = openDb(dbPath);
  let output;
  switch (operation) {
    case 'home':
      output = buildFrontDoor(db, now);
      break;
    case 'ingest':
      if (!options.text) {
        throw new Error('--text is required for ingest');
      }
      output = ingestPayload(db, String(options.text), now);
      break;
    case 'records':
      if (!options.kind) {
        throw new Error('--kind is required for records');
      }
      output = recordsPayload(db, String(options.kind), now);
      break;
    case 'approval':
      if (!options.ref) {
        throw new Error('--ref is required for approval');
      }
      if (!options.decision) {
        throw new Error('--decision is required for approval');
      }
      output = approvalDecisionPayload(db, String(options.ref), String(options.decision), now);
      break;
    case 'action':
      if (!options.kind) {
        throw new Error('--kind is required for action');
      }
      if (!options.ref) {
        throw new Error('--ref is required for action');
      }
      if (!options.action) {
        throw new Error('--action is required for action');
      }
      output = actionPayload(db, String(options.kind), String(options.ref), String(options.action), now);
      break;
    case 'tick':
      output = tickPayload(db, String(options.mode ?? 'all'), now);
      break;
    default:
      throw new Error(`unsupported operation: ${operation}`);
  }

  if (options.json) {
    console.log(JSON.stringify(output, null, 2));
    return;
  }

  console.log(JSON.stringify(output, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

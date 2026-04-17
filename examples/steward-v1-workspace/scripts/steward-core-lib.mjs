import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

export const ROOM_PASSES = ["trash", "dishes", "tools gather", "surfaces", "home base"];
const CASH_WATCH_THRESHOLD_CENTS = -20000;
const DEFAULT_WEEKLY_WINDOW_DAYS = 7;

function isoNow(date = new Date()) {
  return date.toISOString();
}

function normalizeText(value) {
  return value.trim().replace(/\s+/g, " ");
}

function slugify(value) {
  return normalizeText(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function titleCase(value) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function monthKeyForDate(date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function daysInMonth(year, monthIndex) {
  return new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
}

function toUtcDate(year, monthIndex, day) {
  return new Date(Date.UTC(year, monthIndex, day, 12, 0, 0, 0));
}

function centsFromAmountString(raw) {
  if (!raw) {
    return null;
  }
  const cleaned = raw.replace(/[$,]/g, "").trim();
  if (!cleaned) {
    return null;
  }
  const numeric = Number.parseFloat(cleaned);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return Math.round(numeric * 100);
}

function formatCurrency(cents) {
  const value = (cents / 100).toFixed(2);
  return `$${value}`;
}

function ordinalDayToNumber(raw) {
  const match = raw.match(/^(\d{1,2})(st|nd|rd|th)?$/i);
  if (!match) {
    return null;
  }
  const day = Number.parseInt(match[1], 10);
  return day >= 1 && day <= 31 ? day : null;
}

function parseDateInput(raw, now = new Date()) {
  const trimmed = raw.trim().toLowerCase();
  if (trimmed === "today") {
    return now.toISOString().slice(0, 10);
  }
  if (trimmed === "tomorrow") {
    const next = new Date(now);
    next.setUTCDate(next.getUTCDate() + 1);
    return next.toISOString().slice(0, 10);
  }
  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!iso) {
    return null;
  }
  return `${iso[1]}-${iso[2]}-${iso[3]}`;
}

function frequencyToDays(frequency) {
  switch (frequency) {
    case "weekly":
      return 7;
    case "biweekly":
      return 14;
    case "monthly":
      return 30;
    default:
      return null;
  }
}

function upsertValue(current, next) {
  return next == null || next === "" ? current : next;
}

export function openStewardDb(dbPath) {
  mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new DatabaseSync(dbPath);
  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS bills (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      amount_cents INTEGER,
      due_day INTEGER NOT NULL,
      autopay INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS bill_payments (
      id INTEGER PRIMARY KEY,
      bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
      month_key TEXT NOT NULL,
      paid_on TEXT NOT NULL,
      amount_cents INTEGER,
      UNIQUE (bill_id, month_key)
    );

    CREATE TABLE IF NOT EXISTS income (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      amount_cents INTEGER NOT NULL,
      frequency TEXT NOT NULL,
      next_expected_on TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS routines (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      schedule_type TEXT NOT NULL,
      schedule_value TEXT NOT NULL,
      last_done_at TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS important_dates (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      on_date TEXT NOT NULL,
      notes TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY,
      label TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      track TEXT NOT NULL DEFAULT 'general',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS task_steps (
      id INTEGER PRIMARY KEY,
      task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
      step_order INTEGER NOT NULL,
      summary TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      completed_at TEXT,
      UNIQUE (task_id, step_order)
    );

    CREATE TABLE IF NOT EXISTS room_sessions (
      id INTEGER PRIMARY KEY,
      room_name TEXT NOT NULL,
      room_slug TEXT NOT NULL UNIQUE,
      mode TEXT NOT NULL DEFAULT 'standard',
      current_index INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tool_locations (
      id INTEGER PRIMARY KEY,
      tool_name TEXT NOT NULL,
      tool_slug TEXT NOT NULL UNIQUE,
      location TEXT NOT NULL,
      noted_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS state_events (
      id INTEGER PRIMARY KEY,
      state TEXT NOT NULL,
      detail TEXT,
      source TEXT NOT NULL DEFAULT 'manual',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS vault_refs (
      id INTEGER PRIMARY KEY,
      label TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      provider TEXT NOT NULL DEFAULT '1password',
      item_ref TEXT NOT NULL,
      notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);
  return db;
}

function getBillBySlug(db, slug) {
  return db.prepare("SELECT * FROM bills WHERE slug = ?").get(slug) ?? null;
}

function getTaskBySlug(db, slug) {
  return db.prepare("SELECT * FROM tasks WHERE slug = ?").get(slug) ?? null;
}

function getActiveRoom(db) {
  return (
    db
      .prepare(
        "SELECT * FROM room_sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1",
      )
      .get() ?? null
  );
}

function getActiveTask(db) {
  return (
    db
      .prepare("SELECT * FROM tasks WHERE status = 'active' ORDER BY updated_at ASC LIMIT 1")
      .get() ?? null
  );
}

function getPendingTaskStep(db, taskId) {
  return (
    db
      .prepare(
        "SELECT * FROM task_steps WHERE task_id = ? AND status = 'pending' ORDER BY step_order ASC LIMIT 1",
      )
      .get(taskId) ?? null
  );
}

function upsertBill(db, action, now) {
  const slug = slugify(action.name);
  const existing = getBillBySlug(db, slug);
  const timestamp = isoNow(now);
  const amountCents = action.amountCents ?? null;
  if (existing) {
    db.prepare(`
      UPDATE bills
      SET name = ?, amount_cents = ?, due_day = ?, autopay = ?, status = ?, updated_at = ?
      WHERE slug = ?
    `).run(
      titleCase(action.name),
      upsertValue(existing.amount_cents, amountCents),
      action.dueDay,
      action.autopay ? 1 : 0,
      "active",
      timestamp,
      slug,
    );
  } else {
    db.prepare(`
      INSERT INTO bills (name, slug, amount_cents, due_day, autopay, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
    `).run(
      titleCase(action.name),
      slug,
      amountCents,
      action.dueDay,
      action.autopay ? 1 : 0,
      timestamp,
      timestamp,
    );
  }
  return {
    ok: true,
    kind: "bill",
    message: `Saved bill: ${titleCase(action.name)} due on day ${action.dueDay}.`,
  };
}

function markBillPaid(db, action, now) {
  const slug = slugify(action.name);
  const bill = getBillBySlug(db, slug);
  if (!bill) {
    return { ok: false, kind: "bill", message: `Bill not found: ${titleCase(action.name)}.` };
  }
  const timestamp = isoNow(now);
  const monthKey = monthKeyForDate(now);
  db.prepare(
    `
      INSERT INTO bill_payments (bill_id, month_key, paid_on, amount_cents)
      VALUES (?, ?, ?, ?)
      ON CONFLICT (bill_id, month_key) DO UPDATE SET
        paid_on = excluded.paid_on,
        amount_cents = excluded.amount_cents
    `,
  ).run(bill.id, monthKey, timestamp, bill.amount_cents ?? null);
  db.prepare("UPDATE bills SET updated_at = ? WHERE id = ?").run(timestamp, bill.id);
  return { ok: true, kind: "bill", message: `Marked paid: ${bill.name}.` };
}

function updateBillStatus(db, action, now, status) {
  const slug = slugify(action.name);
  const bill = getBillBySlug(db, slug);
  if (!bill) {
    return { ok: false, kind: "bill", message: `Bill not found: ${titleCase(action.name)}.` };
  }
  db.prepare("UPDATE bills SET status = ?, updated_at = ? WHERE id = ?").run(
    status,
    isoNow(now),
    bill.id,
  );
  return {
    ok: true,
    kind: "bill",
    message: `${status === "paused" ? "Paused" : "Removed"} bill: ${bill.name}.`,
  };
}

function upsertIncome(db, action, now) {
  const slug = slugify(action.name);
  const timestamp = isoNow(now);
  const existing = db.prepare("SELECT * FROM income WHERE slug = ?").get(slug) ?? null;
  if (existing) {
    db.prepare(`
      UPDATE income
      SET name = ?, amount_cents = ?, frequency = ?, next_expected_on = ?, status = 'active', updated_at = ?
      WHERE slug = ?
    `).run(
      titleCase(action.name),
      action.amountCents,
      action.frequency,
      action.nextExpectedOn ?? existing.next_expected_on ?? null,
      timestamp,
      slug,
    );
  } else {
    db.prepare(`
      INSERT INTO income (name, slug, amount_cents, frequency, next_expected_on, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
    `).run(
      titleCase(action.name),
      slug,
      action.amountCents,
      action.frequency,
      action.nextExpectedOn ?? null,
      timestamp,
      timestamp,
    );
  }
  return {
    ok: true,
    kind: "income",
    message: `Saved income: ${titleCase(action.name)} ${formatCurrency(action.amountCents)} ${action.frequency}.`,
  };
}

function upsertRoutine(db, action, now) {
  const slug = slugify(action.name);
  const timestamp = isoNow(now);
  const existing = db.prepare("SELECT * FROM routines WHERE slug = ?").get(slug) ?? null;
  if (existing) {
    db.prepare(`
      UPDATE routines
      SET name = ?, schedule_type = ?, schedule_value = ?, status = 'active', updated_at = ?
      WHERE slug = ?
    `).run(titleCase(action.name), action.scheduleType, action.scheduleValue, timestamp, slug);
  } else {
    db.prepare(`
      INSERT INTO routines (name, slug, schedule_type, schedule_value, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, 'active', ?, ?)
    `).run(
      titleCase(action.name),
      slug,
      action.scheduleType,
      action.scheduleValue,
      timestamp,
      timestamp,
    );
  }
  return {
    ok: true,
    kind: "routine",
    message: `Saved routine: ${titleCase(action.name)}.`,
  };
}

function markRoutineDone(db, action, now) {
  const slug = slugify(action.name);
  const routine = db.prepare("SELECT * FROM routines WHERE slug = ?").get(slug) ?? null;
  if (!routine) {
    return { ok: false, kind: "routine", message: `Routine not found: ${titleCase(action.name)}.` };
  }
  db.prepare("UPDATE routines SET last_done_at = ?, updated_at = ? WHERE id = ?").run(
    isoNow(now),
    isoNow(now),
    routine.id,
  );
  return { ok: true, kind: "routine", message: `Marked done: ${routine.name}.` };
}

function upsertImportantDate(db, action, now) {
  const slug = slugify(action.name);
  const timestamp = isoNow(now);
  const existing = db.prepare("SELECT * FROM important_dates WHERE slug = ?").get(slug) ?? null;
  if (existing) {
    db.prepare(`
      UPDATE important_dates
      SET name = ?, on_date = ?, notes = ?, status = 'active', updated_at = ?
      WHERE slug = ?
    `).run(titleCase(action.name), action.onDate, action.notes ?? null, timestamp, slug);
  } else {
    db.prepare(`
      INSERT INTO important_dates (name, slug, on_date, notes, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, 'active', ?, ?)
    `).run(titleCase(action.name), slug, action.onDate, action.notes ?? null, timestamp, timestamp);
  }
  return {
    ok: true,
    kind: "important_date",
    message: `Saved date: ${titleCase(action.name)} on ${action.onDate}.`,
  };
}

function upsertTask(db, action, now) {
  const slug = slugify(action.label);
  const timestamp = isoNow(now);
  const existing = getTaskBySlug(db, slug);
  let taskId = existing?.id ?? null;
  if (existing) {
    db.prepare(
      "UPDATE tasks SET label = ?, track = ?, status = 'active', updated_at = ? WHERE id = ?",
    ).run(action.label, action.track ?? existing.track ?? "general", timestamp, existing.id);
    db.prepare("DELETE FROM task_steps WHERE task_id = ?").run(existing.id);
    taskId = existing.id;
  } else {
    const result = db
      .prepare(
        "INSERT INTO tasks (label, slug, track, status, created_at, updated_at) VALUES (?, ?, ?, 'active', ?, ?)",
      )
      .run(action.label, slug, action.track ?? "general", timestamp, timestamp);
    taskId = Number(result.lastInsertRowid);
  }
  for (const [index, step] of action.steps.entries()) {
    db.prepare(
      "INSERT INTO task_steps (task_id, step_order, summary, status) VALUES (?, ?, ?, 'pending')",
    ).run(taskId, index, step);
  }
  return {
    ok: true,
    kind: "task",
    message: `Saved task: ${action.label}.`,
  };
}

function advanceTask(db, now) {
  const task = getActiveTask(db);
  if (!task) {
    return { ok: false, kind: "task", message: "No active task." };
  }
  const step = getPendingTaskStep(db, task.id);
  if (!step) {
    db.prepare("UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?").run(
      isoNow(now),
      task.id,
    );
    return { ok: true, kind: "task", message: `Task complete: ${task.label}.` };
  }
  db.prepare("UPDATE task_steps SET status = 'done', completed_at = ? WHERE id = ?").run(
    isoNow(now),
    step.id,
  );
  const nextStep = getPendingTaskStep(db, task.id);
  if (!nextStep) {
    db.prepare("UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?").run(
      isoNow(now),
      task.id,
    );
    return { ok: true, kind: "task", message: `Task complete: ${task.label}.` };
  }
  db.prepare("UPDATE tasks SET updated_at = ? WHERE id = ?").run(isoNow(now), task.id);
  return { ok: true, kind: "task", message: `Continue with: ${nextStep.summary}.` };
}

function startRoomSession(db, action, now) {
  const slug = slugify(action.roomName);
  const timestamp = isoNow(now);
  const existing = db.prepare("SELECT * FROM room_sessions WHERE room_slug = ?").get(slug) ?? null;
  if (existing) {
    db.prepare(`
      UPDATE room_sessions
      SET mode = ?, status = 'active', updated_at = ?
      WHERE id = ?
    `).run(action.mode, timestamp, existing.id);
  } else {
    db.prepare(`
      INSERT INTO room_sessions (room_name, room_slug, mode, current_index, status, created_at, updated_at)
      VALUES (?, ?, ?, 0, 'active', ?, ?)
    `).run(titleCase(action.roomName), slug, action.mode, timestamp, timestamp);
  }
  return {
    ok: true,
    kind: "room",
    message: roomPrompt(action.roomName, action.mode, 0),
  };
}

function roomPrompt(roomName, mode, index) {
  if (mode === "micro") {
    return `Start small in ${titleCase(roomName)}: pick up 3 things.`;
  }
  return `Continue with ${titleCase(roomName)}: ${ROOM_PASSES[index]}.`;
}

function advanceRoomSession(db, now) {
  const room = getActiveRoom(db);
  if (!room) {
    return { ok: false, kind: "room", message: "No active room session." };
  }
  const nextIndex = room.mode === "micro" ? 1 : Number(room.current_index) + 1;
  if (room.mode === "micro" || nextIndex >= ROOM_PASSES.length) {
    db.prepare("UPDATE room_sessions SET status = 'done', updated_at = ? WHERE id = ?").run(
      isoNow(now),
      room.id,
    );
    return { ok: true, kind: "room", message: `Room pass complete: ${room.room_name}.` };
  }
  db.prepare("UPDATE room_sessions SET current_index = ?, updated_at = ? WHERE id = ?").run(
    nextIndex,
    isoNow(now),
    room.id,
  );
  return { ok: true, kind: "room", message: roomPrompt(room.room_name, room.mode, nextIndex) };
}

function upsertToolLocation(db, action, now) {
  const slug = slugify(action.toolName);
  const timestamp = isoNow(now);
  db.prepare(
    `
      INSERT INTO tool_locations (tool_name, tool_slug, location, noted_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT (tool_slug) DO UPDATE SET
        tool_name = excluded.tool_name,
        location = excluded.location,
        noted_at = excluded.noted_at
    `,
  ).run(titleCase(action.toolName), slug, normalizeText(action.location), timestamp);
  return {
    ok: true,
    kind: "tool",
    message: `Saved location: ${titleCase(action.toolName)} -> ${normalizeText(action.location)}.`,
  };
}

function readToolLocation(db, action) {
  const slug = slugify(action.toolName);
  const record = db.prepare("SELECT * FROM tool_locations WHERE tool_slug = ?").get(slug) ?? null;
  if (!record) {
    return {
      ok: false,
      kind: "tool",
      message: `No saved location for ${titleCase(action.toolName)}.`,
    };
  }
  return {
    ok: true,
    kind: "tool",
    message: `${record.tool_name} was last seen in ${record.location}.`,
  };
}

function addStateEvent(db, action, now) {
  db.prepare(
    "INSERT INTO state_events (state, detail, source, created_at) VALUES (?, ?, ?, ?)",
  ).run(action.state, action.detail ?? null, action.source ?? "manual", isoNow(now));
  return { ok: true, kind: "state", message: `Logged state: ${action.state}.` };
}

function upsertVaultRef(db, action, now) {
  const slug = slugify(action.label);
  const timestamp = isoNow(now);
  db.prepare(
    `
      INSERT INTO vault_refs (label, slug, provider, item_ref, notes, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (slug) DO UPDATE SET
        label = excluded.label,
        provider = excluded.provider,
        item_ref = excluded.item_ref,
        notes = excluded.notes,
        updated_at = excluded.updated_at
    `,
  ).run(
    action.label,
    slug,
    action.provider ?? "1password",
    action.itemRef,
    action.notes ?? null,
    timestamp,
    timestamp,
  );
  return {
    ok: true,
    kind: "vault",
    message: `Saved vault reference: ${action.label}.`,
  };
}

function getVaultRef(db, action) {
  const slug = slugify(action.label);
  const record = db.prepare("SELECT * FROM vault_refs WHERE slug = ?").get(slug) ?? null;
  if (!record) {
    return { ok: false, kind: "vault", message: `Vault reference not found: ${action.label}.` };
  }
  return {
    ok: true,
    kind: "vault",
    message: `${record.label}: ${record.item_ref}`,
    data: record,
  };
}

function listRows(db, kind) {
  const normalizedKind = kind.toLowerCase();
  switch (normalizedKind) {
    case "bills":
      return db.prepare("SELECT * FROM bills ORDER BY name ASC").all();
    case "payments":
    case "bill_payments":
    case "bill-payments":
      return db
        .prepare(
          `SELECT
            bill_payments.month_key,
            bill_payments.paid_on,
            bill_payments.amount_cents,
            bills.name AS bill_name,
            bills.slug AS bill_slug
          FROM bill_payments
          JOIN bills ON bills.id = bill_payments.bill_id
          ORDER BY bill_payments.paid_on DESC`,
        )
        .all();
    case "income":
      return db.prepare("SELECT * FROM income ORDER BY name ASC").all();
    case "routines":
      return db.prepare("SELECT * FROM routines ORDER BY name ASC").all();
    case "dates":
    case "important_dates":
    case "important-dates":
      return db.prepare("SELECT * FROM important_dates ORDER BY on_date ASC").all();
    case "tasks":
      return db.prepare("SELECT * FROM tasks ORDER BY updated_at ASC").all();
    case "rooms":
    case "room_sessions":
    case "room-sessions":
      return db.prepare("SELECT * FROM room_sessions ORDER BY updated_at DESC").all();
    case "tools":
      return db.prepare("SELECT * FROM tool_locations ORDER BY noted_at DESC").all();
    case "vault":
    case "vault_refs":
    case "vault-refs":
      return db
        .prepare(
          "SELECT label, provider, item_ref, notes, updated_at FROM vault_refs ORDER BY label ASC",
        )
        .all();
    case "states":
    case "state_events":
    case "state-events":
      return db.prepare("SELECT * FROM state_events ORDER BY created_at DESC").all();
    default:
      throw new Error(`Unsupported show kind: ${kind}`);
  }
}

function formatBillSummary(db, now) {
  const bills = listRows(db, "bills");
  if (bills.length === 0) {
    return "No bills saved.";
  }
  const currentMonthKey = monthKeyForDate(now);
  const lines = bills.map((bill) => {
    const parts = [`${bill.name} — due day ${bill.due_day}`];
    if (bill.amount_cents != null) {
      parts.push(formatCurrency(Number(bill.amount_cents)));
    }
    if (bill.autopay) {
      parts.push("autopay");
    }
    if (bill.status !== "active") {
      parts.push(bill.status);
    }
    const paidThisMonth = getPaidMonthKeys(db, bill.id).has(currentMonthKey);
    if (paidThisMonth) {
      parts.push("paid this month");
    }
    return `- ${parts.join(" · ")}`;
  });
  return ["Bills:", ...lines].join("\n");
}

function formatBillPayments(db) {
  const payments = listRows(db, "payments");
  if (payments.length === 0) {
    return "No bill payments saved.";
  }
  const lines = payments.slice(0, 10).map((payment) => {
    const parts = [
      payment.bill_name,
      payment.month_key,
      payment.amount_cents == null
        ? "amount unknown"
        : formatCurrency(Number(payment.amount_cents)),
      `paid ${payment.paid_on.slice(0, 10)}`,
    ];
    return `- ${parts.join(" · ")}`;
  });
  return ["Recent bill payments:", ...lines].join("\n");
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
    return {
      dueDate: toUtcDate(nextYear, nextMonth, nextDueDay),
      monthKey: monthKeyForDate(toUtcDate(nextYear, nextMonth, nextDueDay)),
    };
  }
  return { dueDate: currentOccurrence, monthKey: currentMonthKey };
}

function calendarDayStamp(date) {
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function daysUntil(date, now) {
  return Math.round((calendarDayStamp(date) - calendarDayStamp(now)) / (24 * 60 * 60 * 1000));
}

function getPaidMonthKeys(db, billId) {
  return new Set(
    db
      .prepare("SELECT month_key FROM bill_payments WHERE bill_id = ?")
      .all(billId)
      .map((row) => row.month_key),
  );
}

function computeBillWindows(db, now) {
  const bills = db
    .prepare("SELECT * FROM bills WHERE status = 'active' ORDER BY due_day ASC")
    .all();
  return bills.map((bill) => {
    const paidMonthKeys = getPaidMonthKeys(db, bill.id);
    const nextOccurrence = nextMonthlyOccurrence(Number(bill.due_day), now, paidMonthKeys);
    return {
      bill,
      dueDate: nextOccurrence.dueDate,
      monthKey: nextOccurrence.monthKey,
      daysUntil: daysUntil(nextOccurrence.dueDate, now),
    };
  });
}

function nextExpectedIncomeDate(record, now) {
  if (record.next_expected_on) {
    return new Date(`${record.next_expected_on}T12:00:00.000Z`);
  }
  const frequencyDays = frequencyToDays(record.frequency);
  if (frequencyDays == null) {
    return null;
  }
  const next = new Date(now);
  next.setUTCDate(next.getUTCDate() + frequencyDays);
  return next;
}

export function computeWeeklyCashPressure(db, now = new Date()) {
  const windowEnd = new Date(now);
  windowEnd.setUTCDate(windowEnd.getUTCDate() + DEFAULT_WEEKLY_WINDOW_DAYS);

  let expensesCents = 0;
  for (const entry of computeBillWindows(db, now)) {
    if (entry.bill.amount_cents == null) {
      continue;
    }
    if (entry.dueDate.getTime() <= windowEnd.getTime()) {
      expensesCents += Number(entry.bill.amount_cents);
    }
  }

  let incomeCents = 0;
  const incomeRows = db
    .prepare("SELECT * FROM income WHERE status = 'active' ORDER BY name ASC")
    .all();
  for (const record of incomeRows) {
    const expected = nextExpectedIncomeDate(record, now);
    if (!expected) {
      continue;
    }
    if (expected.getTime() <= windowEnd.getTime()) {
      incomeCents += Number(record.amount_cents);
    }
  }

  const deltaCents = incomeCents - expensesCents;
  const label =
    deltaCents >= 0 ? "stable" : deltaCents >= CASH_WATCH_THRESHOLD_CENTS ? "watch" : "tight";
  return {
    incomeCents,
    expensesCents,
    deltaCents,
    label,
    text: `Weekly cash pressure: ${label}. Income ${formatCurrency(incomeCents)}, expenses ${formatCurrency(expensesCents)}, delta ${formatCurrency(deltaCents)}.`,
  };
}

function routineDueMessage(record, now) {
  if (record.schedule_type === "every") {
    const intervalMinutes = Number.parseInt(record.schedule_value, 10);
    if (!Number.isFinite(intervalMinutes)) {
      return null;
    }
    const lastDone = record.last_done_at ? new Date(record.last_done_at) : null;
    if (!lastDone) {
      return `Do this now: ${record.name}.`;
    }
    const elapsedMinutes = Math.floor((now.getTime() - lastDone.getTime()) / (60 * 1000));
    if (elapsedMinutes >= intervalMinutes) {
      return `Do this now: ${record.name}.`;
    }
  }
  if (record.schedule_type === "at") {
    const currentTime = now.toISOString().slice(11, 16);
    const lastDoneDay = record.last_done_at ? record.last_done_at.slice(0, 10) : null;
    const today = now.toISOString().slice(0, 10);
    if (currentTime >= record.schedule_value && lastDoneDay !== today) {
      return `Do this now: ${record.name}.`;
    }
  }
  return null;
}

export function getNextAction(db, now = new Date()) {
  for (const entry of computeBillWindows(db, now)) {
    if (entry.daysUntil < 0) {
      return { kind: "bill", text: `Handle this first: ${entry.bill.name} is overdue.` };
    }
    if (entry.daysUntil === 0) {
      return { kind: "bill", text: `Handle this first: ${entry.bill.name} is due today.` };
    }
    if (entry.daysUntil <= 2) {
      return {
        kind: "bill",
        text: `Plan this now: ${entry.bill.name} is due in ${entry.daysUntil} day(s).`,
      };
    }
  }

  const routines = db
    .prepare("SELECT * FROM routines WHERE status = 'active' ORDER BY name ASC")
    .all();
  for (const routine of routines) {
    const message = routineDueMessage(routine, now);
    if (message) {
      return { kind: "routine", text: message };
    }
  }

  const dateRow =
    db
      .prepare("SELECT * FROM important_dates WHERE status = 'active' ORDER BY on_date ASC LIMIT 1")
      .get() ?? null;
  if (dateRow) {
    const eventDate = new Date(`${dateRow.on_date}T12:00:00.000Z`);
    const deltaDays = daysUntil(eventDate, now);
    if (deltaDays <= 0) {
      return { kind: "important_date", text: `Handle this first: ${dateRow.name} is today.` };
    }
    if (deltaDays <= 2) {
      return {
        kind: "important_date",
        text: `Prepare now: ${dateRow.name} is in ${deltaDays} day(s).`,
      };
    }
  }

  const activeRoom = getActiveRoom(db);
  if (activeRoom) {
    return {
      kind: "room",
      text: roomPrompt(activeRoom.room_name, activeRoom.mode, Number(activeRoom.current_index)),
    };
  }

  const activeTask = getActiveTask(db);
  if (activeTask) {
    const step = getPendingTaskStep(db, activeTask.id);
    if (step) {
      return { kind: "task", text: `Continue with: ${step.summary}.` };
    }
  }

  const cash = computeWeeklyCashPressure(db, now);
  if (cash.label === "tight") {
    return { kind: "cash", text: "Protect cash this week: cover essentials first." };
  }
  if (cash.label === "watch") {
    return { kind: "cash", text: "Stay tight this week: handle essentials before optional work." };
  }

  return { kind: "steady", text: "HEARTBEAT_OK" };
}

export function buildHeartbeat(db, now = new Date()) {
  const nextAction = getNextAction(db, now);
  return nextAction.text === "HEARTBEAT_OK" ? "HEARTBEAT_OK" : nextAction.text;
}

export function parseUtterance(rawText, now = new Date()) {
  const text = normalizeText(rawText);

  let match = text.match(
    /^add bill (.+?) amount (\$?[\d,]+(?:\.\d+)?) due (\d{1,2}(?:st|nd|rd|th)?)(?: (autopay))?$/i,
  );
  if (match) {
    return {
      type: "add_bill",
      name: match[1],
      dueDay: ordinalDayToNumber(match[3]),
      amountCents: centsFromAmountString(match[2] ?? null),
      autopay: Boolean(match[4]),
    };
  }

  match = text.match(
    /^add bill (.+?) due (\d{1,2}(?:st|nd|rd|th)?)(?: amount (\$?[\d,]+(?:\.\d+)?))?(?: (autopay))?$/i,
  );
  if (match) {
    return {
      type: "add_bill",
      name: match[1],
      dueDay: ordinalDayToNumber(match[2]),
      amountCents: centsFromAmountString(match[3] ?? null),
      autopay: Boolean(match[4]),
    };
  }

  match = text.match(/^(?:paid|mark paid) (.+?)(?: bill)?$/i);
  if (match) {
    return { type: "pay_bill", name: match[1] };
  }

  match = text.match(/^pause bill (.+)$/i);
  if (match) {
    return { type: "pause_bill", name: match[1] };
  }

  match = text.match(/^remove bill (.+)$/i);
  if (match) {
    return { type: "remove_bill", name: match[1] };
  }

  match = text.match(
    /^add income (.+?) (\$?[\d,]+(?:\.\d+)?) (monthly|weekly|biweekly|once)(?: on (\d{4}-\d{2}-\d{2}))?$/i,
  );
  if (match) {
    return {
      type: "add_income",
      name: match[1],
      amountCents: centsFromAmountString(match[2]),
      frequency: match[3].toLowerCase(),
      nextExpectedOn: match[4] ?? null,
    };
  }

  match = text.match(/^add routine (.+?) every (\d+)(m|h|d)$/i);
  if (match) {
    const numeric = Number.parseInt(match[2], 10);
    const multiplier =
      match[3].toLowerCase() === "h" ? 60 : match[3].toLowerCase() === "d" ? 1440 : 1;
    return {
      type: "add_routine",
      name: match[1],
      scheduleType: "every",
      scheduleValue: String(numeric * multiplier),
    };
  }

  match = text.match(/^add routine (.+?) at (\d{2}:\d{2})$/i);
  if (match) {
    return {
      type: "add_routine",
      name: match[1],
      scheduleType: "at",
      scheduleValue: match[2],
    };
  }

  match = text.match(/^(?:done routine|completed routine) (.+)$/i);
  if (match) {
    return { type: "done_routine", name: match[1] };
  }

  match = text.match(/^add date (.+?) on (today|tomorrow|\d{4}-\d{2}-\d{2})(?: note (.+))?$/i);
  if (match) {
    return {
      type: "add_date",
      name: match[1],
      onDate: parseDateInput(match[2], now),
      notes: match[3] ?? null,
    };
  }

  match = text.match(/^start room (.+?)(?: (micro))?$/i);
  if (match) {
    return { type: "start_room", roomName: match[1], mode: match[2] ? "micro" : "standard" };
  }

  if (/^(?:room done|done room)$/i.test(text) || /^done$/i.test(text)) {
    return { type: "room_done" };
  }

  match = text.match(/^add task (.+?)(?: track ([a-z-]+))?: (.+)$/i);
  if (match) {
    const rawSteps = match[3]
      .split("|")
      .map((step) => normalizeText(step))
      .filter(Boolean);
    return { type: "add_task", label: match[1], track: match[2] ?? "general", steps: rawSteps };
  }

  if (/^(?:task done|done task)$/i.test(text)) {
    return { type: "task_done" };
  }

  match = text.match(/^(?:using|tool) (.+?) (?:in|at) (.+)$/i);
  if (match) {
    return { type: "set_tool_location", toolName: match[1], location: match[2] };
  }

  match = text.match(/^(?:where is|where's) (?:the )?(.+)$/i);
  if (match) {
    return { type: "find_tool", toolName: match[1] };
  }

  match = text.match(/^log state (steady|stuck|avoiding|overloaded|activated)(?: because (.+))?$/i);
  if (match) {
    return { type: "log_state", state: match[1].toLowerCase(), detail: match[2] ?? null };
  }

  match = text.match(/^add vault ref (.+?) (op:\/\/\S+)(?: note (.+))?$/i);
  if (match) {
    return { type: "add_vault_ref", label: match[1], itemRef: match[2], notes: match[3] ?? null };
  }

  match = text.match(/^show vault ref (.+)$/i);
  if (match) {
    return { type: "show_vault_ref", label: match[1] };
  }

  if (/^(?:show|list) bills$/i.test(text)) {
    return { type: "show_bills" };
  }

  if (/^(?:show|list) payments$/i.test(text)) {
    return { type: "show_payments" };
  }

  if (/^(?:continue|what's next|whats next|next)$/i.test(text)) {
    return { type: "next_action" };
  }

  if (/^heartbeat$/i.test(text)) {
    return { type: "heartbeat" };
  }

  return { type: "unknown", text };
}

export function applyAction(db, action, now = new Date()) {
  switch (action.type) {
    case "add_bill":
      return upsertBill(db, action, now);
    case "pay_bill":
      return markBillPaid(db, action, now);
    case "pause_bill":
      return updateBillStatus(db, action, now, "paused");
    case "remove_bill":
      return updateBillStatus(db, action, now, "removed");
    case "add_income":
      return upsertIncome(db, action, now);
    case "add_routine":
      return upsertRoutine(db, action, now);
    case "done_routine":
      return markRoutineDone(db, action, now);
    case "add_date":
      return upsertImportantDate(db, action, now);
    case "start_room":
      return startRoomSession(db, action, now);
    case "room_done":
      return advanceRoomSession(db, now);
    case "add_task":
      return upsertTask(db, action, now);
    case "task_done":
      return advanceTask(db, now);
    case "set_tool_location":
      return upsertToolLocation(db, action, now);
    case "find_tool":
      return readToolLocation(db, action);
    case "log_state":
      return addStateEvent(db, action, now);
    case "add_vault_ref":
      return upsertVaultRef(db, action, now);
    case "show_vault_ref":
      return getVaultRef(db, action);
    case "show_bills":
      return { ok: true, kind: "bill", message: formatBillSummary(db, now) };
    case "show_payments":
      return { ok: true, kind: "bill_payment", message: formatBillPayments(db) };
    case "next_action": {
      const nextAction = getNextAction(db, now);
      return { ok: true, kind: nextAction.kind, message: nextAction.text };
    }
    case "heartbeat":
      return { ok: true, kind: "heartbeat", message: buildHeartbeat(db, now) };
    case "unknown":
      return { ok: false, kind: "unknown", message: `Unrecognized input: ${action.text}` };
    default:
      throw new Error(`Unhandled action type: ${action.type}`);
  }
}

export function handleUtterance(db, text, now = new Date()) {
  const action = parseUtterance(text, now);
  return {
    action,
    result: applyAction(db, action, now),
  };
}

export function showKind(db, kind) {
  return listRows(db, kind);
}

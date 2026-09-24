// Uses only injected, supported app tools. No daemon, network transport or model.
function payload(result) {
  if (result.isError) throw new Error("app wait tool failed");
  return result.content ? JSON.parse(result.content.find(x => x.type === "text").text) : result;
}

function reduceWait(previous, result) {
  const next = JSON.parse(JSON.stringify(previous));
  const data = payload(result);
  next.calls += 1;
  if (data.errors && Object.keys(data.errors).length) {
    next.status = "attention";
    next.reason = "app connection/target error; reconcile before resuming";
    return next;
  }
  if (data.wake?.reason && !["turnCompleted", "actionableStatus"].includes(data.wake.reason)) {
    next.status = "attention";
    next.reason = "app wait interrupted: " + data.wake.reason;
    return next;
  }
  for (const poll of data.polls || []) {
    const target = next.targets.find(t => t.thread_id === poll.thread?.id && t.host_id === poll.thread?.hostId);
    if (!target) continue;
    if (poll.cursor) next.cursors[target.task_id] = poll.cursor;
    const flags = poll.thread.status?.activeFlags || [];
    const turn = poll.latestTurn;
    if (flags.length || ["failed", "interrupted"].includes(turn?.status) ||
        (data.wake?.reason === "actionableStatus" && (!data.wake.threadId || data.wake.threadId === target.thread_id))) {
      next.status = "attention";
      next.reason = "worker needs attention: " + target.task_id;
      return next;
    }
    if (turn && turn.id !== target.turn_id) {
      next.status = "attention";
      next.reason = "resolve the original execution turn: " + target.task_id;
      return next;
    }
    if (turn?.status === "completed" && !next.completed.includes(target.task_id)) {
      next.completed.push(target.task_id);
    }
  }
  // A terminal turn is only a review hint. Command/RESULT/process checks remain mandatory.
  if (data.wake?.reason === "actionableStatus") {
    next.status = "attention";
    next.reason = "app task needs attention";
  } else if (next.completed.length === next.targets.length ||
      (next.review_on === "first" && next.completed.length)) next.status = "ready";
  else if (!data.timedOut && !data.wake && !(data.polls || []).length) {
    next.status = "attention";
    next.reason = "wait interrupted or returned no observable targets";
  }
  return next;
}

async function waitForBatch(checkpoint, { wait, save, now = Date.now }) {
  if (checkpoint.mode === "user") return { status: "waiting_user", batch_id: checkpoint.id };
  if (checkpoint.status !== "waiting") return { status: "inspect_checkpoint", batch_id: checkpoint.id };
  let current = checkpoint;
  while (current.status === "waiting") {
    if (now() >= current.deadline_ms) {
      current = await save({ ...current, status: "attention", reason: "approved wait deadline reached" });
      break;
    }
    const pending = current.targets.filter(t => !current.completed.includes(t.task_id));
    if (!pending.length) {
      current = await save({ ...current, status: "ready" });
      break;
    }
    // Rotate bounded groups so >8 targets do not starve later failures.
    const batches = [];
    for (let i = 0; i < pending.length; i += 8) batches.push(pending.slice(i, i + 8));
    for (const batch of batches) {
      const timeoutMs = Math.max(0, Math.min(50000 / batches.length, current.deadline_ms - now()));
      const targets = batch.map(t => ({ threadId: t.thread_id, hostId: t.host_id,
        ...(current.cursors[t.task_id] ? { afterCursor: current.cursors[t.task_id] } : {}) }));
      try {
        current = await save(reduceWait(current, await wait({ targets, timeoutMs: Math.floor(timeoutMs) })));
      } catch (error) {
        // Never retry an uncertain checkpoint write with guessed revision/cursors.
        return { status: "attention", reason: String(error), checkpoint: current };
      }
      if (current.status !== "waiting") break;
    }
  }
  return { status: current.status, reason: current.reason, batch_id: current.id,
    completed: current.completed, tool_calls: current.calls };
}

module.exports = { reduceWait, waitForBatch };

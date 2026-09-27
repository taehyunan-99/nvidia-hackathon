export type ActivityEvent = {
  candidate_id: string; step_id: string; updated_at: string; reason?: string | null;
  activity: { event_id: string; kind: string; name: string; phase: string; actor: string; reason?: string; next_action?: string; available_tools?: string[]; skill?: { id: string; revision: string }; verification?: {status: string; checks: {name: string; status: string}[]} };
};

// Older runs mark rule continuation stages as "workflow". A recorded fallback
// is required to identify those stages; never infer a model decision from them.
export function displayEvents(events: ActivityEvent[]): ActivityEvent[] {
  const ruleCandidates = new Set<string>();
  return events.flatMap((event) => {
    if (event.activity.kind === "fallback") ruleCandidates.add(event.candidate_id);
    if (event.activity.kind !== "stage") return [event];
    if (event.activity.actor === "rule") return [event];
    if (ruleCandidates.has(event.candidate_id)) return [{ ...event, activity: { ...event.activity, actor: "rule" } }];
    return [];
  });
}

export function actorLabel(event?: ActivityEvent): string {
  if (!event) return "대기";
  if (event.activity.actor === "rule") return "규칙 처리";
  if (event.activity.actor === "code") return event.activity.name === "check_input" ? "자동 입력 검사" : "코드 처리";
  if (event.activity.actor === "agent") return "에이전트";
  return "단계 기록";
}

export function followUp(events: ActivityEvent[], toolNames: string[]): { label: string; actions: string[] } {
  for (const { activity } of events.slice().reverse()) {
    if (activity.kind === "fallback") return { label: "현재 처리", actions: ["continue_by_rule"] };
    if (activity.kind === "stage" && activity.actor === "rule") return { label: ({running: "현재 규칙 단계", completed: "완료한 단계", skipped: "생략한 단계", failed: "실패한 단계", held: "보류한 단계"}[activity.phase] ?? "규칙 단계"), actions: [activity.name] };
    if (activity.kind === "tool" && activity.phase === "failed") return { label: "후속 안내", actions: ["실패 기록 확인"] };
    if (activity.kind === "tool" && activity.phase === "running") return { label: "실행 중", actions: [activity.name] };
    if (activity.available_tools !== undefined) return activity.available_tools.length
      ? { label: "가능한 도구", actions: activity.available_tools }
      : { label: "후속 안내", actions: [activity.next_action ?? "종료"] };
    if (!activity.next_action) continue;
    const actions = activity.next_action.split(", ");
    // Legacy tool completion records contain availability, not a chosen action.
    const available = activity.kind === "tool" && actions.every((name) => toolNames.includes(name));
    return { label: available ? "가능한 도구" : "후속 안내", actions };
  }
  return { label: "후속 안내", actions: [] };
}

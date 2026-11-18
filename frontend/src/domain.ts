// Types and small pure helpers shared by the UI. All validation and permission
// rules live on the server (command_centre/work.py); nothing here is trusted.
export const stages = ['To do', 'In progress', 'Waiting', 'Blocked', 'In review', 'Changes requested', 'Done'] as const;
export type Stage = (typeof stages)[number];

export type Person = {
  id: string;
  name: string;
  email: string;
  department: string;
  role: 'Admin' | 'Manager' | 'Member';
  companies: string[];
  departments: string[];
};
export type Step = { id: string; title: string; owner: string; done: boolean };
export type Task = {
  id: string;
  title: string;
  company: string;
  department: string;
  project: string;
  owner: string;
  contributors: string[];
  reviewer: string;
  reviewRequired: boolean;
  status: Stage;
  priority: 'Low' | 'Medium' | 'High';
  start: string;
  due: string;
  milestone: boolean;
  estimate: number;
  dependencies: string[];
  waitingOn: string;
  blockReason: string;
  description: string;
  evidence: string;
  steps: Step[];
  created: string;
  updated: string;
  completed: string;
};
export type Event = {
  id: string;
  at: string;
  actor: string;
  task: string;
  company: string;
  department: string;
  owner: string;
  type: string;
  detail: string;
  from: string;
  to: string;
};
export type Workspace = {
  id: string;
  name: string;
  ownerId: string;
  revision: number;
  companies: { id: string; name: string }[];
  departments: { id: string; name: string }[];
  people: Person[];
  projects: { id: string; name: string; company: string }[];
  tasks: Task[];
  events: Event[];
};
export type Action = { type: string; [key: string]: unknown };

/** crypto.randomUUID() only exists in secure contexts (https / localhost); fall back for plain http. */
export function uid(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  const b = new Uint8Array(16);
  if (c?.getRandomValues) c.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function blankTask(w: Workspace, p: Person): Task {
  return {
    id: uid(),
    title: '',
    company: w.companies[0]?.id || '',
    department: p.department || '',
    project: '',
    owner: p.id,
    contributors: [],
    reviewer: '',
    reviewRequired: false,
    status: 'To do',
    priority: 'Medium',
    start: '',
    due: '',
    milestone: false,
    estimate: 0,
    dependencies: [],
    waitingOn: '',
    blockReason: '',
    description: '',
    evidence: '',
    steps: [],
    created: '',
    updated: '',
    completed: '',
  };
}

export function scheduleWarnings(w: Workspace, t: Task): string[] {
  return t.dependencies.flatMap((id) => {
    const dep = w.tasks.find((x) => x.id === id);
    return dep?.due && t.start && dep.due > t.start ? [`${dep.title} finishes after this task starts`] : [];
  });
}

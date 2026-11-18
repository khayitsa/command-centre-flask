'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Command,
  LayoutDashboard,
  ListTodo,
  Building2,
  FolderOpen,
  Users,
  ChartNoAxesGantt,
  BarChart3,
  ClipboardCheck,
  History,
  Plus,
  Search,
  ArrowUpRight,
  Check,
  X,
  Download,
  RefreshCw,
  ChevronRight,
  Flag,
  Upload,
  AlertCircle,
  LogOut,
} from 'lucide-react';
import { blankTask, stages, uid, scheduleWarnings, type Workspace, type Task, type Person, type Action } from './domain';
import { api, csv, download, signOut, ApiError } from './api';
import { parseCSV } from './csv';
type View =
  'Overview' | 'My work' | 'All tasks' | 'Projects' | 'Companies' | 'Departments' | 'People' | 'Reviews' | 'Gantt' | 'Reports' | 'Activity';
const dateNow = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const addDays = (d: string, n: number) => new Date(Date.parse(d + 'T00:00:00Z') + n * 86400000).toISOString().slice(0, 10);
const days = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="field">
    <span>{label}</span>
    {children}
  </label>
);
export default function CommandCentre() {
  const [w, setW] = useState<Workspace | null>(null),
    [me, setMe] = useState<Person | null>(null),
    [workspaces, setWorkspaces] = useState<{ id: string; name: string }[]>([]),
    [legacy, setLegacy] = useState(''),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [error, setError] = useState(''),
    [mode, setMode] = useState(''),
    [view, setView] = useState<View>('Overview'),
    [query, setQuery] = useState(''),
    [company, setCompany] = useState(''),
    [department, setDepartment] = useState(''),
    [owner, setOwner] = useState(''),
    [project, setProject] = useState(''),
    [status, setStatus] = useState(''),
    [dialog, setDialog] = useState(''),
    [task, setTask] = useState<Task | null>(null),
    [person, setPerson] = useState<Person | null>(null),
    [focusTask, setFocusTask] = useState(''),
    [timeline, setTimeline] = useState(dateNow()),
    [zoom, setZoom] = useState(22),
    [reportFrom, setReportFrom] = useState(''),
    [reportTo, setReportTo] = useState('');
  const modal = useRef<HTMLDialogElement>(null),
    file = useRef<HTMLInputElement>(null);
  const today = dateNow();
  const signedIn = typeof document !== 'undefined' ? document.getElementById('root')?.dataset.user || '' : '';
  function absorb(r: any) {
    if (r.workspace) {
      setW(r.workspace);
      setMe(r.me);
      setFocusTask((id) => (r.workspace.tasks.some((t: Task) => t.id === id) ? id : ''));
    }
    setMode(r.development ? 'Development server' : 'Shared workspace');
  }
  async function load(id?: string) {
    setError('');
    try {
      const r = await api(undefined, id);
      if (id) absorb(r);
      else {
        setWorkspaces(r.workspaces);
        setMode(r.development ? 'Development server' : 'Shared workspace');
        if (r.workspaces.length) {
          const result = await api(undefined, r.workspaces[0].id);
          absorb(result);
        }
      }
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setReady(true);
    }
  }
  useEffect(() => {
    load();
    try {
      setLegacy(localStorage.getItem('command-centre-v1') || '');
    } catch {}
  }, []);
  useEffect(() => {
    const el = modal.current;
    if (!el) return;
    if (dialog) {
      if (!el.open) el.showModal();
    } else if (el.open) el.close();
  }, [dialog]);
  async function mutate(action: Action) {
    if (!w) return false;
    setBusy(true);
    setError('');
    try {
      const r = await api({ workspace: w.id, revision: w.revision, action });
      absorb(r);
      setMessage('Saved · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      return true;
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 409) {
        setError(
          'Someone else changed this workspace. It has been refreshed with their changes; your last change was not saved. Please check and try again.',
        );
        try {
          absorb(await api(undefined, w.id));
        } catch {}
      } else setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  function close() {
    setDialog('');
    setError('');
  }
  function newTask() {
    if (!w || !me) return;
    if (!w.companies.length) {
      setDialog('company');
      return;
    }
    setTask(blankTask(w, me));
    setDialog('task');
  }
  const name = (kind: 'people' | 'companies' | 'departments' | 'projects', id: string) =>
    w?.[kind].find((x) => x.id === id)?.name || 'Unassigned';
  const active = w?.tasks.find((t) => t.id === focusTask);
  const matches = (t: Task, ignoreStatus = false) =>
    (!company || t.company === company) &&
    (!department || t.department === department) &&
    (!owner || t.owner === owner) &&
    (!project || t.project === project) &&
    (ignoreStatus || !status || t.status === status) &&
    `${t.title} ${t.description} ${name('people', t.owner)}`.toLowerCase().includes(query.toLowerCase());
  const filtered = (w?.tasks || []).filter((t) => matches(t));
  const reportTasks = (w?.tasks || []).filter((t) => matches(t, true));
  useEffect(() => {
    if (['detail', 'schedule'].includes(dialog) && !active) setDialog('');
  }, [dialog, active]);
  const visible = filtered.filter(
    (t) =>
      view !== 'My work' ||
      t.owner === me?.id ||
      t.contributors.includes(me?.id || '') ||
      t.steps.some((s) => s.owner === me?.id && !s.done),
  );
  const pending = (w?.tasks || []).filter((t) => t.status === 'In review' && t.reviewer === me?.id);
  const open = (w?.tasks || []).filter((t) => t.status !== 'Done');
  const admin = me?.role === 'Admin';
  function resetFilters() {
    setCompany('');
    setDepartment('');
    setOwner('');
    setProject('');
    setStatus('');
    setQuery('');
  }
  function taskOpen(t: Task) {
    setFocusTask(t.id);
    setDialog('detail');
  }
  async function transition(t: Task, next: string) {
    let note = '';
    if (['Blocked', 'Waiting', 'Changes requested'].includes(next)) {
      const result = prompt(next === 'Changes requested' ? 'What needs changing?' : 'What is blocking progress or being waited on?');
      if (result === null) return;
      note = result;
    }
    await mutate({ type: 'transition', id: t.id, status: next, note });
  }
  function exportTasks() {
    if (!w) return;
    download(
      'command-centre-tasks.csv',
      csv([
        [
          'title',
          'company',
          'department',
          'project',
          'owner',
          'reviewer',
          'reviewRequired',
          'priority',
          'start',
          'due',
          'estimate',
          'description',
          'evidence',
        ],
        ...visible.map((t) => [
          t.title,
          name('companies', t.company),
          t.department ? name('departments', t.department) : '',
          t.project ? name('projects', t.project) : '',
          name('people', t.owner),
          t.reviewer ? name('people', t.reviewer) : '',
          t.reviewRequired,
          t.priority,
          t.start,
          t.due,
          t.estimate,
          t.description,
          t.evidence,
        ]),
      ]),
      'text/csv',
    );
  }
  async function importTasks(f: File) {
    if (!w || !me) return;
    try {
      if (f.size > 2000000) throw Error('Maximum import size: 2 MB');
      const rows = parseCSV(await f.text());
      const headers = rows.shift()?.map((x) => x.trim());
      if (!headers?.includes('title') || !headers.includes('company'))
        throw Error('CSV requires title and company columns. Download the template in All tasks.');
      const match = (kind: 'companies' | 'departments' | 'projects' | 'people', value: string, required = false, companyId = '') => {
        const found = (w[kind] as { id: string; name: string; company?: string }[]).filter(
          (x) => x.name.toLowerCase() === value.toLowerCase() && (kind !== 'projects' || x.company === companyId),
        );
        if (found.length !== 1 && (value || required))
          throw Error(
            kind === 'projects'
              ? `Set up a project called “${value}” in that task's company first.`
              : `Set up a unique ${kind} entry for “${value}” first.`,
          );
        return found[0]?.id || '';
      };
      const cell = (v?: string) => (v ?? '').trim().replace(/^'(?=[=+@\t\r-])/, '');
      const priorities = ['Low', 'Medium', 'High'];
      const tasks = rows
        .filter((r) => r.some(Boolean))
        .map((r) => {
          const a = Object.fromEntries(headers.map((h, i) => [h, cell(r[i])]));
          const companyId = match('companies', a.company, true);
          return {
            ...blankTask(w, me),
            title: a.title,
            company: companyId,
            department: match('departments', a.department || ''),
            project: match('projects', a.project || '', false, companyId),
            owner: a.owner ? match('people', a.owner, true) : me.id,
            reviewer: match('people', a.reviewer || ''),
            reviewRequired: a.reviewRequired.toLowerCase() === 'true',
            priority: priorities.find((p) => p.toLowerCase() === a.priority.toLowerCase()) || a.priority || 'Medium',
            start: a.start || '',
            due: a.due || '',
            estimate: Number(a.estimate || 0),
            description: a.description || '',
            evidence: a.evidence || '',
          };
        });
      if (!tasks.length) throw Error('No task rows found');
      if (confirm(`Add ${tasks.length} tasks as To do? This does not replace existing tasks. Re-importing creates duplicates.`))
        await mutate({ type: 'import', tasks });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (file.current) file.current.value = '';
    }
  }
  async function formSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      v = (k: string) => String(f.get(k) || '').trim();
    if (dialog === 'workspace') {
      setBusy(true);
      try {
        const r = await api({ type: 'create', name: v('name') });
        resetFilters();
        setFocusTask('');
        setView('Overview');
        absorb(r);
        setWorkspaces((xs) => [...xs, { id: r.workspace.id, name: r.workspace.name }]);
        close();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
      return;
    }
    let action: Action;
    if (['company', 'department', 'project'].includes(dialog))
      action = {
        type: 'entity',
        kind: dialog === 'company' ? 'companies' : dialog === 'department' ? 'departments' : 'projects',
        name: v('name'),
        company: v('company'),
      };
    else if (dialog === 'person' && person) action = { type: 'person', person };
    else if (dialog === 'task' && task) action = { type: 'task', task };
    else if (dialog === 'schedule' && active) {
      const affected = w?.tasks.filter((t) => t.dependencies.includes(active.id)) || [];
      let shift = false;
      if (f.get('shift')) {
        shift = confirm(
          `Also shift dependent tasks by the same number of days? This starts with ${affected.length} direct dependants and follows their dependency chains. Cancel moves only this task.`,
        );
      }
      action = { type: 'schedule', id: active.id, start: v('start'), due: active.milestone ? v('start') : v('due'), shift };
    } else return;
    if (await mutate(action)) close();
  }

  const selectFilter = (label: string, value: string, set: (v: string) => void, items: { id: string; name: string }[]) => (
    <label className="filter-label">
      <span>{label}</span>
      <select aria-label={label} value={value} onChange={(e) => set(e.target.value)}>
        <option value="">All {label.toLowerCase()}</option>
        {items.map((x) => (
          <option key={x.id} value={x.id}>
            {x.name}
          </option>
        ))}
      </select>
    </label>
  );
  const Badge = ({ t }: { t: Task }) => <span className={'status ' + t.status.toLowerCase().replaceAll(' ', '-')}>{t.status}</span>;
  function TaskTable({ tasks }: { tasks: Task[] }) {
    return tasks.length ? (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task & next step</th>
              <th>Company / project</th>
              <th>Owner</th>
              <th>Status</th>
              <th>Due</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td>
                  <button className="task-name" onClick={() => taskOpen(t)}>
                    {t.milestone ? <Flag size={15} /> : t.status === 'Done' ? <Check size={16} /> : <span className="task-circle" />}
                    {t.title}
                  </button>
                  <small>
                    {t.steps.length ? `${t.steps.filter((s) => s.done).length}/${t.steps.length} steps complete` : t.priority + ' priority'}
                    {t.dependencies.length ? ' · ' + t.dependencies.length + ' prerequisites' : ''}
                  </small>
                </td>
                <td>
                  {name('companies', t.company)}
                  <small>{t.project ? name('projects', t.project) : 'Standalone task'}</small>
                </td>
                <td>
                  {name('people', t.owner)}
                  <small>{t.department ? name('departments', t.department) : ''}</small>
                </td>
                <td>
                  <Badge t={t} />
                  {t.blockReason && <small>{t.blockReason}</small>}
                </td>
                <td className={t.due && t.due < today && t.status !== 'Done' ? 'overdue' : ''}>{t.due || 'No deadline'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <div className="empty">
        <ListTodo size={30} />
        <h3>No tasks in this view.</h3>
        <p>Add a task or adjust your filters.</p>
        <button onClick={newTask}>
          <Plus size={16} />
          Create task
        </button>
      </div>
    );
  }
  const nav = [
    ['Overview', LayoutDashboard],
    ['My work', ListTodo],
    ['All tasks', ListTodo],
    ['Projects', FolderOpen],
    ['Gantt', ChartNoAxesGantt],
    ['Reviews', ClipboardCheck],
    ['Reports', BarChart3],
    ['Activity', History],
    ['Companies', Building2],
    ['Departments', Building2],
    ['People', Users],
  ] as const;
  const reportEvents = (w?.events || []).filter(
    (e) =>
      (!company || e.company === company) &&
      (!department || e.department === department) &&
      (!owner || e.owner === owner) &&
      (!project || w?.tasks.find((t) => t.id === e.task)?.project === project) &&
      (!reportFrom || e.at.slice(0, 10) >= reportFrom) &&
      (!reportTo || e.at.slice(0, 10) <= reportTo),
  );
  function reportRows(kind: 'owner' | 'department') {
    return [...new Set([...reportTasks.map((t) => t[kind]), ...reportEvents.map((e) => e[kind])].filter(Boolean))].map((id) => {
      const ts = reportTasks.filter((t) => t[kind] === id),
        ev = reportEvents.filter((e) => e[kind] === id);
      return [
        name(kind === 'owner' ? 'people' : 'departments', id),
        ts.filter((t) => t.status !== 'Done').length,
        ts.filter((t) => t.status === 'Done').length,
        ts.filter((t) => t.status === 'In review').length,
        ts.filter((t) => t.status === 'Blocked' || t.status === 'Waiting').length,
        ts.filter((t) => t.due && t.due < today && t.status !== 'Done').length,
        ev.filter((e) => e.to === 'Done').length,
        ev.filter((e) => e.to === 'Changes requested').length,
        Math.round(ts.filter((t) => t.status !== 'Done').reduce((n, t) => n + t.estimate, 0) * 100) / 100,
      ];
    });
  }
  const rptHeaders = [
    'Group',
    'Open now',
    'Done now',
    'In review',
    'Blocked / waiting',
    'Overdue',
    'Completions in period',
    'Returned in period',
    'Estimated open hours',
  ];
  if (!ready) return <main className="loading">Opening Command Centre…</main>;
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <span className="mark">
            <Command size={21} />
          </span>
          Command Centre
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <select
          aria-label="Workspace"
          className="workspace-select"
          value={w?.id || ''}
          onChange={(e) => {
            resetFilters();
            setFocusTask('');
            load(e.target.value);
          }}
        >
          <option value="" disabled>
            Select workspace
          </option>
          {workspaces.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
        <button className="text-button" onClick={() => setDialog('workspace')}>
          + New workspace
        </button>
        <nav>
          {nav.map(([label, Icon]) => (
            <button
              key={label}
              className={view === label ? 'selected' : ''}
              onClick={() => {
                setView(label);
                setFocusTask('');
              }}
            >
              <Icon size={17} />
              {label}
              {label === 'Reviews' && pending.length > 0 && <span className="count">{pending.length}</span>}
            </button>
          ))}
        </nav>
        <div className="aside-bottom">
          <span className="dot" />
          {mode}
          <p>
            {me?.name} · {me?.role}
          </p>
          <p className="signed-in">{signedIn}</p>
        </div>
      </aside>
      <div className="main">
        <header>
          <span>
            {w?.name || 'Welcome'} <span className="slash">/</span> {view}
          </span>
          <div className="actions">
            <span className="local">{mode}</span>
            {w && (
              <button aria-label="Refresh workspace" onClick={() => load(w.id)}>
                <RefreshCw size={15} />
              </button>
            )}
            {/* In the header (not the sidebar footer) so it stays reachable on phones. */}
            <button aria-label="Sign out" title={signedIn ? `Sign out ${signedIn}` : 'Sign out'} onClick={() => signOut()}>
              <LogOut size={15} />
            </button>
          </div>
        </header>
        <main>
          {legacy && (
            <div className="notice">
              Earlier preview data is still on this device.{' '}
              <button onClick={() => download('earlier-command-centre-backup.json', legacy)}>Export earlier data</button> It has not been
              moved into this workspace.
            </div>
          )}
          {error && !dialog && (
            <div role="alert" className="error-banner">
              <AlertCircle size={18} />
              {error}
            </div>
          )}
          <div className="heading">
            <div>
              <div className="eyebrow">WORK CONNECTED. PROGRESS VISIBLE.</div>
              <h1>{view === 'Overview' ? 'Know what moves next.' : view}</h1>
              <p>
                {view === 'Overview' ? 'One flow from responsibility to delivery.' : 'The same work, viewed from the right perspective.'}
              </p>
            </div>
            <button className="primary" disabled={busy} onClick={() => (w ? newTask() : setDialog('workspace'))}>
              <Plus size={17} />
              {w ? 'New task' : 'Create workspace'}
            </button>
          </div>
          {!w ? (
            <section className="welcome">
              <div>
                <span className="pill">YOUR ORGANISATION. YOUR WAY OF WORKING.</span>
                <h2>Build a home for your work.</h2>
                <p>
                  Set up companies, departments and people.
                  <br />
                  Connect everyday tasks to projects, handovers and decisions.
                </p>
                <button className="primary" onClick={() => setDialog('workspace')}>
                  Create a workspace <ArrowUpRight size={17} />
                </button>
              </div>
              <div className="welcome-art" aria-hidden="true">
                <div className="art-circle">
                  <Command size={66} />
                </div>
              </div>
            </section>
          ) : (
            <>
              {view === 'Overview' && (
                <>
                  {!w.companies.length && (
                    <section className="welcome">
                      <div>
                        <span className="pill">LET’S GET SET UP</span>
                        <h2>Give your work a structure.</h2>
                        <p>
                          Start with a company, then add departments and people.
                          <br />
                          Your first task can stand alone or belong to a project.
                        </p>
                        <button className="primary" onClick={() => setDialog('company')}>
                          Add your first company <Plus size={16} />
                        </button>
                      </div>
                    </section>
                  )}
                  <div className="stats">
                    {[
                      ['Open work', open.length],
                      ['Needs a decision', w.tasks.filter((t) => t.status === 'In review').length],
                      ['Blocked / waiting', open.filter((t) => ['Blocked', 'Waiting'].includes(t.status)).length],
                      ['Overdue', open.filter((t) => t.due && t.due < today).length],
                    ].map(([label, n]) => (
                      <section key={label}>
                        <span>{label}</span>
                        <strong>{n}</strong>
                      </section>
                    ))}
                  </div>
                  <div className="section-heading">
                    <h2>What needs attention</h2>
                    <button className="text-button" onClick={() => setView('All tasks')}>
                      View all work <ArrowUpRight size={15} />
                    </button>
                  </div>
                  <section className="panel">
                    <TaskTable
                      tasks={open
                        .filter(
                          (t) =>
                            ['Blocked', 'Waiting', 'In review', 'Changes requested'].includes(t.status) ||
                            (t.due && t.due <= addDays(today, 7)),
                        )
                        .slice(0, 15)}
                    />
                  </section>
                  <p className="report-note">
                    Open tasks due within seven days, waiting for a decision, blocked or returned for changes. Visibility follows your
                    access scope.
                  </p>
                </>
              )}
              {['All tasks', 'My work', 'Gantt', 'Reports'].includes(view) && (
                <section className="panel filters-wrap">
                  <div className="filters">
                    <label className="search">
                      <Search size={17} />
                      <input
                        aria-label="Search tasks"
                        placeholder="Find a task…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    {selectFilter('Companies', company, setCompany, w.companies)}
                    {selectFilter('Departments', department, setDepartment, w.departments)}
                    {selectFilter('People', owner, setOwner, w.people)}
                    {selectFilter('Projects', project, setProject, w.projects)}
                    {view !== 'Reports' &&
                      selectFilter(
                        'Statuses',
                        status,
                        setStatus,
                        stages.map((s) => ({ id: s, name: s })),
                      )}
                    <button onClick={resetFilters}>Clear</button>
                  </div>
                </section>
              )}
              {['All tasks', 'My work'].includes(view) && (
                <>
                  <div className="section-heading">
                    <h2>{visible.length} tasks</h2>
                    <div className="actions">
                      <button onClick={exportTasks}>
                        <Download size={15} />
                        Export CSV
                      </button>
                      {admin && (
                        <button onClick={() => file.current?.click()}>
                          <Upload size={15} />
                          Import CSV
                        </button>
                      )}
                    </div>
                  </div>
                  <section className="panel">
                    <TaskTable tasks={visible} />
                  </section>
                  <p className="report-note">
                    CSV import adds new tasks as To do. Create companies and people first; names must match.{' '}
                    <a href="/static/task-template.csv" download>
                      Download template
                    </a>
                  </p>
                </>
              )}
              {['Companies', 'Departments', 'Projects', 'People'].includes(view) && (
                <>
                  <div className="section-heading">
                    <h2>Your {view.toLowerCase()}</h2>
                    {admin && (
                      <button
                        onClick={() => {
                          if (view === 'People') {
                            setPerson({ id: uid(), name: '', email: '', department: '', role: 'Member', companies: [], departments: [] });
                            setDialog('person');
                          } else setDialog(view === 'Companies' ? 'company' : view === 'Departments' ? 'department' : 'project');
                        }}
                      >
                        <Plus size={16} />
                        Add{' '}
                        {view === 'People'
                          ? 'person'
                          : view === 'Companies'
                            ? 'company'
                            : view === 'Departments'
                              ? 'department'
                              : 'project'}
                      </button>
                    )}
                  </div>
                  <div className="cards">
                    {(view === 'Companies'
                      ? w.companies
                      : view === 'Departments'
                        ? w.departments
                        : view === 'Projects'
                          ? w.projects
                          : w.people
                    ).map((item) => {
                      const ts = w.tasks.filter((t) =>
                        view === 'Companies'
                          ? t.company === item.id
                          : view === 'Departments'
                            ? t.department === item.id
                            : view === 'Projects'
                              ? t.project === item.id
                              : t.owner === item.id,
                      );
                      return (
                        <section className="entity" key={item.id}>
                          <span className="avatar">{item.name[0]}</span>
                          <h2>{item.name}</h2>
                          <p>
                            {view === 'People'
                              ? (item as Person).role
                              : 'company' in item
                                ? name('companies', String(item.company))
                                : view === 'Companies'
                                  ? 'Company'
                                  : 'Department'}
                          </p>
                          <strong>
                            {ts.filter((t) => t.status !== 'Done').length} open · {ts.filter((t) => t.status === 'Done').length} completed
                          </strong>
                          <button
                            className="text-button"
                            onClick={() => {
                              resetFilters();
                              if (view === 'Companies') setCompany(item.id);
                              if (view === 'Departments') setDepartment(item.id);
                              if (view === 'Projects') setProject(item.id);
                              if (view === 'People') setOwner(item.id);
                              setView('All tasks');
                            }}
                          >
                            View work <ArrowUpRight size={15} />
                          </button>
                          {view === 'People' && admin && (
                            <button
                              className="text-button"
                              onClick={() => {
                                setPerson(item as Person);
                                setDialog('person');
                              }}
                            >
                              Edit access
                            </button>
                          )}
                        </section>
                      );
                    })}
                  </div>
                  {view === 'People' && (
                    <p className="report-note">
                      Names represent people, not additional sign-ins. An exact email grants workspace access when that person signs in with
                      an account using that email (accounts are created by the server administrator). Empty scope selections mean all
                      companies / departments.
                    </p>
                  )}
                </>
              )}
              {view === 'Reviews' && (
                <>
                  <section className="welcome compact">
                    <div>
                      <h2>Your decision queue</h2>
                      <p>Review the output and handover steps. Approve the work or explain what needs changing.</p>
                    </div>
                    <strong className="large-number">{pending.length}</strong>
                  </section>
                  <section className="panel">
                    <TaskTable tasks={pending} />
                  </section>
                </>
              )}
              {view === 'Gantt' && (
                <>
                  <div className="section-heading">
                    <div className="actions">
                      <Field label="Timeline starts">
                        <input type="date" value={timeline} onChange={(e) => setTimeline(e.target.value || today)} />
                      </Field>
                      <Field label="Zoom">
                        <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
                          <option value={22}>Days</option>
                          <option value={8}>Weeks</option>
                        </select>
                      </Field>
                    </div>
                    <span className="report-note">90-day window · click a bar to move dates</span>
                  </div>
                  <Gantt
                    tasks={filtered}
                    start={timeline}
                    zoom={zoom}
                    onTask={taskOpen}
                    onMove={(t) => {
                      if (['In review', 'Done'].includes(t.status)) {
                        setError(`Reopen or withdraw “${t.title}” before moving its dates.`);
                        return;
                      }
                      setError('');
                      setFocusTask(t.id);
                      setDialog('schedule');
                    }}
                  />
                  <p className="report-note">
                    Arrows show prerequisite relationships. Diamonds are milestones. Dates only shift dependants after explicit
                    confirmation; no silent rescheduling.
                  </p>
                  {filtered.some((t) => !t.start || !t.due) && (
                    <section className="panel">
                      <div className="section-heading inset">
                        <h2>Not yet scheduled</h2>
                      </div>
                      <TaskTable tasks={filtered.filter((t) => !t.start || !t.due)} />
                    </section>
                  )}
                </>
              )}
              {view === 'Reports' && (
                <>
                  <div className="report-heading">
                    <div>
                      <h2>Current position & activity over time</h2>
                      <p>Current task filters apply to snapshot counts. Event dates and original assignments determine period activity.</p>
                    </div>
                    <div className="actions">
                      <button
                        onClick={() =>
                          download(
                            'command-centre-report.csv',
                            csv([
                              ['Workspace', w.name],
                              ['Generated', new Date().toISOString()],
                              ['Company', company ? name('companies', company) : 'All'],
                              ['Department', department ? name('departments', department) : 'All'],
                              ['Owner', owner ? name('people', owner) : 'All'],
                              ['Period', reportFrom || 'Beginning', reportTo || 'Now'],
                              [],
                              rptHeaders,
                              ...reportRows('department'),
                              [],
                              rptHeaders,
                              ...reportRows('owner'),
                            ]),
                            'text/csv',
                          )
                        }
                      >
                        <Download size={15} />
                        Export report
                      </button>
                      <button onClick={() => window.print()}>Print / PDF</button>
                    </div>
                  </div>
                  <div className="report-dates">
                    <Field label="Activity from">
                      <input type="date" value={reportFrom} onChange={(e) => setReportFrom(e.target.value)} />
                    </Field>
                    <Field label="Activity through">
                      <input type="date" value={reportTo} min={reportFrom} onChange={(e) => setReportTo(e.target.value)} />
                    </Field>
                  </div>
                  {(['department', 'owner'] as const).map((kind) => (
                    <section className="panel report-table" key={kind}>
                      <h2>By {kind === 'owner' ? 'person' : 'department'}</h2>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              {rptHeaders.map((h) => (
                                <th key={h}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {reportRows(kind).map((r, i) => (
                              <tr key={i}>
                                {r.map((c, j) => (
                                  <td key={j}>{c}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  ))}
                  <p className="report-note">
                    Completions count recorded transitions to Done, including repeat completions after reopening. Estimates are planned
                    hours, not timesheets or measured capacity. Tasks without a department remain visible in All tasks but do not enter a
                    named department row. Dates for activity are UTC.
                  </p>
                </>
              )}
              {view === 'Activity' && (
                <>
                  <div className="section-heading">
                    <h2>Workspace record</h2>
                    <button onClick={() => download('command-centre-data.json', JSON.stringify(w, null, 2))}>
                      <Download size={15} />
                      Export visible data
                    </button>
                  </div>
                  <Activity events={w.events} />
                </>
              )}
            </>
          )}
          <div className="bottom-note" role="status">
            <span>
              <span className="dot" />
              {message || 'Tasks, decisions and progress—connected.'}
            </span>
            <span>{w ? `Revision ${w.revision}` : 'Start with a blank workspace'}</span>
          </div>
        </main>
      </div>
      <input
        type="file"
        accept=".csv,text/csv"
        hidden
        ref={file}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) importTasks(f);
        }}
      />
      <dialog ref={modal} onCancel={close} className={dialog === 'detail' ? 'wide-dialog' : ''}>
        <div className="dialog-heading">
          <h2>
            {dialog === 'detail'
              ? active?.title
              : dialog === 'task'
                ? w?.tasks.some((t) => t.id === task?.id)
                  ? 'Edit task'
                  : 'Create task'
                : dialog === 'schedule'
                  ? 'Move task dates'
                  : dialog === 'workspace'
                    ? 'Create workspace'
                    : dialog === 'person'
                      ? 'Person & access'
                      : `Add ${dialog}`}
          </h2>
          <button aria-label="Close dialog" onClick={close}>
            <X size={18} />
          </button>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        {dialog === 'detail' && active && w && me ? (
          <>
            <div className="detail-meta">
              <Badge t={active} />
              <span>
                {name('companies', active.company)} / {active.project ? name('projects', active.project) : 'Standalone'}
              </span>
            </div>
            <p className="description">{active.description || 'No brief added.'}</p>
            <div className="detail-grid">
              <div>
                <small>Accountable owner</small>
                <strong>{name('people', active.owner)}</strong>
              </div>
              <div>
                <small>Department</small>
                <strong>{name('departments', active.department)}</strong>
              </div>
              <div>
                <small>Timeline</small>
                <strong>
                  {active.start || 'Not scheduled'} → {active.due || 'No deadline'}
                </strong>
              </div>
              <div>
                <small>Reviewer</small>
                <strong>{active.reviewRequired ? name('people', active.reviewer) : 'Review not required'}</strong>
              </div>
            </div>
            {active.contributors.length > 0 && <p>Contributors: {active.contributors.map((id) => name('people', id)).join(', ')}</p>}
            {active.dependencies.length > 0 && (
              <div className="dependency-list">
                <h3>Prerequisites</h3>
                {active.dependencies.map((id) => {
                  const t = w.tasks.find((t) => t.id === id);
                  return t ? (
                    <button key={id} onClick={() => taskOpen(t)}>
                      {t.status === 'Done' ? <Check size={14} /> : <ChevronRight size={14} />} {t.title} · {t.status}
                    </button>
                  ) : null;
                })}
              </div>
            )}
            {active.blockReason && (
              <div className="notice">
                {active.blockReason}
                {active.waitingOn ? ' · Waiting on ' + name('people', active.waitingOn) : ''}
              </div>
            )}
            {scheduleWarnings(w, active).map((s) => (
              <div className="notice" key={s}>
                {s}
              </div>
            ))}
            <h3>Handover steps</h3>
            {active.steps.length ? (
              active.steps.map((s) => (
                <label className="step-row" key={s.id}>
                  <input
                    type="checkbox"
                    checked={s.done}
                    disabled={
                      busy ||
                      ['In review', 'Done'].includes(active.status) ||
                      !(admin || me.role === 'Manager' || active.owner === me.id || s.owner === me.id)
                    }
                    onChange={(e) => mutate({ type: 'step', id: active.id, step: s.id, done: e.target.checked })}
                  />
                  <span>
                    {s.title}
                    <small>{name('people', s.owner)}</small>
                  </span>
                </label>
              ))
            ) : (
              <p>No separate handover steps.</p>
            )}
            <h3>Output / evidence</h3>
            <p className="description">{active.evidence || 'No output added yet.'}</p>
            <div className="actions wrap">
              {active.status === 'In review' && active.reviewer === me.id ? (
                <>
                  <button disabled={busy} className="primary" onClick={() => transition(active, 'Done')}>
                    Approve & complete
                  </button>
                  <button disabled={busy} onClick={() => transition(active, 'Changes requested')}>
                    Request changes
                  </button>
                </>
              ) : null}
              {(admin || me.role === 'Manager' || active.owner === me.id) && (
                <>
                  {!['In review', 'Done'].includes(active.status) && (
                    <>
                      <button
                        onClick={() => {
                          setTask(structuredClone(active));
                          setDialog('task');
                        }}
                      >
                        Edit details
                      </button>
                      <button onClick={() => setDialog('schedule')}>Move dates</button>
                      <select
                        aria-label="Change task status"
                        value={active.status}
                        disabled={busy}
                        onChange={(e) => transition(active, e.target.value)}
                      >
                        {stages
                          .filter(
                            (s) =>
                              s === active.status ||
                              (s !== 'Changes requested' &&
                                (s !== 'In review' || active.reviewRequired) &&
                                (s !== 'Done' || !active.reviewRequired)),
                          )
                          .map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                      </select>
                    </>
                  )}
                  {active.status === 'Done' && <button onClick={() => transition(active, 'In progress')}>Reopen task</button>}
                  {active.status === 'In review' && <button onClick={() => transition(active, 'In progress')}>Withdraw for editing</button>}
                </>
              )}
            </div>
            <form
              className="update-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const form = e.currentTarget,
                  note = String(new FormData(form).get('note'));
                if (await mutate({ type: 'comment', id: active.id, note })) form.reset();
              }}
            >
              <Field label="Progress update">
                <input name="note" required maxLength={500} placeholder="What changed? What happens next?" />
              </Field>
              <button disabled={busy}>Add update</button>
            </form>
            <h3>Activity</h3>
            <Activity events={w.events.filter((e) => e.task === active.id)} />
          </>
        ) : (
          <form onSubmit={formSubmit} key={dialog + (task?.id || '') + (person?.id || '')}>
            {['workspace', 'company', 'department', 'project'].includes(dialog) && (
              <Field label="Name">
                <input name="name" required maxLength={120} placeholder={dialog === 'workspace' ? 'Your workspace' : `${dialog} name`} />
              </Field>
            )}
            {dialog === 'project' && w && (
              <Field label="Company">
                <select required name="company">
                  {w.companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {dialog === 'task' && task && w && (
              <>
                <Field label="Task title">
                  <input required maxLength={300} value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} />
                </Field>
                <Field label="Brief & definition of done">
                  <textarea rows={3} value={task.description} onChange={(e) => setTask({ ...task, description: e.target.value })} />
                </Field>
                <div className="form-grid">
                  {(['company', 'department', 'project', 'owner', 'reviewer', 'waitingOn'] as const).map((field) => (
                    <Field
                      key={field}
                      label={
                        {
                          company: 'Company',
                          department: 'Department',
                          project: 'Project (optional)',
                          owner: 'Accountable owner',
                          reviewer: 'Reviewer',
                          waitingOn: 'Waiting on (optional)',
                        }[field]
                      }
                    >
                      <select
                        required={field === 'company' || field === 'owner'}
                        value={task[field]}
                        onChange={(e) =>
                          setTask({ ...task, [field]: e.target.value, ...(field === 'company' ? { project: '', dependencies: [] } : {}) })
                        }
                      >
                        <option value="">{['company', 'owner'].includes(field) ? 'Choose…' : 'None'}</option>
                        {(field === 'company'
                          ? w.companies
                          : field === 'department'
                            ? w.departments
                            : field === 'project'
                              ? w.projects.filter((p) => p.company === task.company)
                              : w.people
                        ).map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                  ))}
                  <Field label="Priority">
                    <select value={task.priority} onChange={(e) => setTask({ ...task, priority: e.target.value as Task['priority'] })}>
                      {['Low', 'Medium', 'High'].map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Estimated hours">
                    <input
                      type="number"
                      min="0"
                      max="100000"
                      step="0.25"
                      value={task.estimate}
                      onChange={(e) => setTask({ ...task, estimate: Number(e.target.value) })}
                    />
                  </Field>
                  <Field label="Start date">
                    <input
                      type="date"
                      value={task.start}
                      onChange={(e) => setTask({ ...task, start: e.target.value, ...(task.milestone ? { due: e.target.value } : {}) })}
                    />
                  </Field>
                  <Field label="Due date">
                    <input
                      type="date"
                      min={task.start}
                      value={task.due}
                      disabled={task.milestone}
                      onChange={(e) => setTask({ ...task, due: e.target.value })}
                    />
                  </Field>
                </div>
                <div className="check-options">
                  <label>
                    <input
                      type="checkbox"
                      checked={task.reviewRequired}
                      onChange={(e) => setTask({ ...task, reviewRequired: e.target.checked })}
                    />
                    Requires approval
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={task.milestone}
                      onChange={(e) => setTask({ ...task, milestone: e.target.checked, ...(e.target.checked ? { due: task.start } : {}) })}
                    />
                    Milestone (one date)
                  </label>
                </div>
                <Field label="Contributors">
                  <select
                    multiple
                    value={task.contributors}
                    onChange={(e) => setTask({ ...task, contributors: Array.from(e.target.selectedOptions, (o) => o.value) })}
                  >
                    {w.people.map((p) => (
                      <option value={p.id} key={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Prerequisite tasks">
                  <select
                    multiple
                    value={task.dependencies}
                    onChange={(e) => setTask({ ...task, dependencies: Array.from(e.target.selectedOptions, (o) => o.value) })}
                  >
                    {w.tasks
                      .filter((t) => t.company === task.company && t.id !== task.id)
                      .map((t) => (
                        <option value={t.id} key={t.id}>
                          {t.title}
                        </option>
                      ))}
                  </select>
                </Field>
                <p className="report-note">Use Ctrl / Command to select several items on a computer.</p>
                <h3>Handover steps</h3>
                {task.steps.map((s, i) => (
                  <div className="step-edit" key={s.id}>
                    <input
                      aria-label={`Step ${i + 1} title`}
                      required
                      value={s.title}
                      onChange={(e) =>
                        setTask({ ...task, steps: task.steps.map((x) => (x.id === s.id ? { ...x, title: e.target.value } : x)) })
                      }
                    />
                    <select
                      aria-label={`Step ${i + 1} owner`}
                      required
                      value={s.owner}
                      onChange={(e) =>
                        setTask({ ...task, steps: task.steps.map((x) => (x.id === s.id ? { ...x, owner: e.target.value } : x)) })
                      }
                    >
                      {w.people.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      aria-label={`Remove step ${i + 1}`}
                      onClick={() => setTask({ ...task, steps: task.steps.filter((x) => x.id !== s.id) })}
                    >
                      <X size={15} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    setTask({ ...task, steps: [...task.steps, { id: uid(), title: '', owner: task.owner || me!.id, done: false }] })
                  }
                >
                  <Plus size={14} />
                  Add step
                </button>
                <Field label="Output, links or evidence">
                  <textarea rows={3} value={task.evidence} onChange={(e) => setTask({ ...task, evidence: e.target.value })} />
                </Field>
              </>
            )}
            {dialog === 'person' && person && w && (
              <>
                <Field label="Name">
                  <input required value={person.name} onChange={(e) => setPerson({ ...person, name: e.target.value })} />
                </Field>
                <Field label="Sign-in email (optional)">
                  <input type="email" value={person.email} onChange={(e) => setPerson({ ...person, email: e.target.value })} />
                </Field>
                <Field label="Role">
                  <select value={person.role} onChange={(e) => setPerson({ ...person, role: e.target.value as Person['role'] })}>
                    {['Admin', 'Manager', 'Member'].map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </Field>
                <p className="report-note">
                  Admins manage structure and access. Managers manage tasks in scope. Members manage their own tasks and assigned steps.
                  Only the assigned reviewer can approve.
                </p>
                <Field label="Home department">
                  <select value={person.department} onChange={(e) => setPerson({ ...person, department: e.target.value })}>
                    <option value="">None</option>
                    {w.departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </Field>
                {(['companies', 'departments'] as const).map((kind) => (
                  <Field key={kind} label={`Allowed ${kind} (empty = all)`}>
                    <select
                      multiple
                      value={person[kind]}
                      onChange={(e) => setPerson({ ...person, [kind]: Array.from(e.target.selectedOptions, (o) => o.value) })}
                    >
                      {w[kind].map((x) => (
                        <option value={x.id} key={x.id}>
                          {x.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                ))}
                <p className="notice">
                  Saving an email grants access to this workspace to whoever signs in with an account using that email. No invitation email
                  is sent. Admins have full workspace access.
                </p>
              </>
            )}
            {dialog === 'schedule' && active && (
              <>
                <p>
                  Move dates for <strong>{active.title}</strong>.
                </p>
                <div className="form-grid">
                  <Field label="Start date">
                    <input name="start" type="date" defaultValue={active.start} />
                  </Field>
                  <Field label="Due date">
                    <input name="due" type="date" defaultValue={active.due} disabled={active.milestone} />
                  </Field>
                </div>
                {active.milestone && <p className="report-note">Milestones have a single date.</p>}
                <label className="step-row">
                  <input type="checkbox" name="shift" />
                  Also propose shifting dependent tasks
                </label>
                <p className="report-note">
                  You’ll confirm before any dependent task moves. The server checks permission for every affected task.
                </p>
              </>
            )}
            <div className="dialog-actions">
              <button type="button" onClick={close}>
                Cancel
              </button>
              <button className="primary" disabled={busy}>
                {busy ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        )}
      </dialog>
    </div>
  );
}
function Activity({ events }: { events: Workspace['events'] }) {
  return (
    <div className="activity">
      {[...events]
        .reverse()
        .slice(0, 200)
        .map((e) => (
          <article key={e.id}>
            <span className="activity-dot" />
            <div>
              <strong>{e.type}</strong>
              <p>{e.detail}</p>
              <small>
                {e.actor} · {new Date(e.at).toLocaleString()}
              </small>
            </div>
          </article>
        ))}
      {!events.length && <p>No activity yet. Changes will appear here.</p>}
      {events.length > 200 && <p>Showing the latest 200 events. Export visible data for the complete history.</p>}
    </div>
  );
}
function Gantt({
  tasks,
  start,
  zoom,
  onTask,
  onMove,
}: {
  tasks: Task[];
  start: string;
  zoom: number;
  onTask: (t: Task) => void;
  onMove: (t: Task) => void;
}) {
  const rows = tasks.filter((t) => t.start && t.due),
    width = 90 * zoom,
    height = rows.length * 52;
  const x = (date: string) => days(start, date) * zoom;
  return (
    <div className="gantt panel">
      <div className="gantt-names">
        <div className="gantt-name-head">Task</div>
        {rows.map((t) => (
          <button key={t.id} onClick={() => onTask(t)}>
            {t.title}
            <small>{t.status}</small>
          </button>
        ))}
      </div>
      <div className="gantt-scroll">
        <div className="gantt-canvas" style={{ width, minHeight: height + 44 }}>
          <div className="gantt-dates">
            {Array.from({ length: 90 }, (_, i) => (
              <span key={i} style={{ width: zoom }}>
                {zoom === 22
                  ? i === 0 || addDays(start, i).endsWith('-01')
                    ? addDays(start, i).slice(5)
                    : addDays(start, i).slice(8)
                  : i % 7 === 0
                    ? addDays(start, i).slice(5)
                    : ''}
              </span>
            ))}
          </div>
          <div style={{ position: 'relative', height }}>
            <svg className="dependency-lines" width={width} height={height} aria-label="Task dependency connections">
              <defs>
                <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6" fill="#8aa298" />
                </marker>
              </defs>
              {rows.flatMap((t, i) =>
                t.dependencies.map((dep) => {
                  const index = rows.findIndex((x) => x.id === dep);
                  if (index < 0) return null;
                  const x1 = x(rows[index].due) + zoom,
                    x2 = x(t.start),
                    y1 = index * 52 + 26,
                    y2 = i * 52 + 26;
                  return (
                    <path
                      key={t.id + dep}
                      d={`M${x1},${y1} H${x1 + 8} V${y2} H${x2}`}
                      fill="none"
                      stroke="#8aa298"
                      strokeWidth="1.5"
                      markerEnd="url(#arrow)"
                    />
                  );
                }),
              )}
            </svg>
            {rows.map((t, i) => {
              const left = Math.max(0, x(t.start)),
                right = Math.min(width, x(t.due) + zoom);
              return (
                <div key={t.id} className="gantt-lane" style={{ top: i * 52, backgroundSize: `${zoom * 7}px 100%` }}>
                  {right > left && (
                    <button
                      title={`${t.title}: ${t.start} to ${t.due}. Click to move dates.`}
                      aria-label={`Move dates for ${t.title}`}
                      className={'gantt-bar ' + (t.status === 'Done' ? 'complete ' : '') + (t.milestone ? 'milestone' : '')}
                      style={{ left, width: t.milestone ? 18 : Math.max(18, right - left) }}
                      onClick={() => onMove(t)}
                    >
                      {t.milestone ? '◆' : t.title}
                    </button>
                  )}
                </div>
              );
            })}
            {x(dateNow()) >= 0 && x(dateNow()) <= width && (
              <div className="today-line" style={{ left: x(dateNow()) }}>
                <span>Today</span>
              </div>
            )}
          </div>
        </div>
      </div>
      {!rows.length && <p className="empty">Add start and due dates to see tasks on the timeline.</p>}
    </div>
  );
}

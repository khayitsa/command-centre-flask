export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** GET with no body lists / loads workspaces; POST with a body creates or changes one. */
export async function api(body?: Record<string, unknown>, id = ''): Promise<any> {
  const response = await fetch('/api/workspace' + (id ? '?id=' + encodeURIComponent(id) : ''), {
    method: body ? 'POST' : 'GET',
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data: any = {};
  try {
    data = await response.json();
  } catch {
    /* non-JSON error page */
  }
  if (response.status === 401) {
    location.assign('/login');
    throw new ApiError('Your session has ended. Please sign in again.', 401);
  }
  if (!response.ok) throw new ApiError(data.error || `Request failed (${response.status})`, response.status);
  return data;
}

export async function signOut() {
  try {
    await fetch('/logout', { method: 'POST', credentials: 'same-origin' });
  } finally {
    location.assign('/login');
  }
}

export function download(name: string, content: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a); // Firefox needs the link to be in the document
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** CSV with every cell quoted. Leading = + - @ tab CR are neutralised so spreadsheets never run a cell as a formula. */
export function csv(rows: unknown[][]) {
  return rows
    .map((row) =>
      row
        .map(
          (v) =>
            '"' +
            String(v ?? '')
              .replace(/^[=+@\t\r-]/, "'$&")
              .replaceAll('"', '""') +
            '"',
        )
        .join(','),
    )
    .join('\r\n');
}

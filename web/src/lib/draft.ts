// Older drafts had no owner, so they cannot be safely attributed to the account opening the sheet.
export function accountDraft(name: string, owner: number | undefined) {
  const key = owner ? `${name}:${owner}` : null;
  try { localStorage.removeItem(name); } catch { /* private mode */ }
  return {
    read(): string | null {
      try { return key ? localStorage.getItem(key) : null; } catch { return null; }
    },
    save(value: string | null) {
      if (!key) return;
      try {
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, value);
      } catch { /* private mode: the form still works in memory */ }
    },
  };
}

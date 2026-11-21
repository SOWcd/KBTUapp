import { onMount } from 'svelte';
import { DRAFT_AGE, recovery } from './state/recovery';

export function draftRecord<T>(owner: string | null, key: string, store = recovery) {
  const belongsToAccount = () => owner !== null && store.scope() === owner;
  let last: string | undefined;
  let editedAt = -Infinity;
  let pending: { json: string; at: number } | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  function flush() {
    clearTimeout(timer);
    if (pending) store.write(owner, key, pending.json, pending.at);
    pending = undefined;
  }
  function track(value: T | null) {
    const json = JSON.stringify(value);
    if (json === last) return;
    const changed = last !== undefined;
    last = json;
    if (!changed || !belongsToAccount()) return;
    clearTimeout(timer);
    editedAt = store.now();
    pending = { json, at: editedAt };
    timer = setTimeout(flush, 300);
  }
  function discard(at = store.now()) {
    if (editedAt <= at) {
      clearTimeout(timer);
      pending = undefined;
      last = 'null';
      editedAt = at;
    }
    store.write(owner, key, 'null', at);
  }
  const read = () => belongsToAccount() ? store.read<T>(owner, key, DRAFT_AGE) : null;
  return { read, track, flush, discard };
}

export function useDraft<T>(key: string | (() => string | null)) {
  // Bind to the verified account that opened the form, even if the form loads its record later.
  const owner = recovery.scope();
  let name: string | null = null;
  let draft: ReturnType<typeof draftRecord<T>> | undefined;
  function record() {
    const next = typeof key === 'string' ? key : key();
    if (next !== name) {
      draft?.flush();
      name = next;
      draft = name ? draftRecord<T>(owner, name) : undefined;
    }
    return draft;
  }
  const flush = () => draft?.flush();
  onMount(() => {
    const hide = () => { if (document.hidden) flush(); };
    document.addEventListener('visibilitychange', hide);
    window.addEventListener('pagehide', flush);
    return () => {
      document.removeEventListener('visibilitychange', hide);
      window.removeEventListener('pagehide', flush);
      flush();
    };
  });
  return {
    read: () => record()?.read() ?? null,
    track: (value: T | null) => record()?.track(value),
    stamp: recovery.now,
    discard: (at?: number) => record()?.discard(at),
  };
}

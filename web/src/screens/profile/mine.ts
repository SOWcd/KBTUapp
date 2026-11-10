// My photo and nick, changed from two places: "About me" (SettingsSheet) and my photo on the lanyard (Me, through
// SettingsList.photoMenu). One module so both run the same jobs, one at a time.
import { api, ApiErr, type Me } from '../../lib/api';
import { session } from '../../lib/state/session.svelte';
import { say, ui } from '../../lib/state/ui.svelte';
import { sheets } from '../../lib/state/sheets';
import { t } from '../../lib/i18n/index.svelte';
import { haptic } from '../../lib/tg';
import type { MenuItem } from '../../ui/menu';

let busy = false;
function oops(e: unknown) {
  haptic.error();
  say(e instanceof ApiErr && e.message === 'nick' ? t('look.badNick') : e instanceof ApiErr && e.message === 'not_an_image' ? t('look.badPhoto') : t('common.error'), 'warning_3d');
}
// one change of my photo or nick at a time; `word`: what the capsule says meanwhile (an upload takes a moment)
async function work(job: () => Promise<Me>, msg: (m: Me) => string, word = '') {
  if (busy) return;
  busy = true; ui.busy = word;
  try { const m = await job(); session.me = m; haptic.ok(); say(msg(m), 'sparkles_3d'); } catch (e) { oops(e); } finally { busy = false; ui.busy = ''; }
}

// ---- the photo: Telegram's (it refreshes by itself) or my own ----
// one hidden picker kept in the page (iOS opens none that isn't in the document)
let file: HTMLInputElement | undefined;
function pick() {
  if (!file) {
    file = document.createElement('input');
    file.type = 'file'; file.accept = 'image/*'; file.hidden = true;
    file.onchange = () => void upload(file!.files?.[0]);
    document.body.append(file);
  }
  file.click();
}
async function upload(f: File | undefined) {
  if (file) file.value = ''; // the same photo picked again opens the crop again
  const cut = f && await sheets.cropPhoto(f);
  if (cut) void work(() => api.uploadMyPhoto(cut), () => t('look.photoSet'), t('look.uploading'));
}
async function dropOwn() {
  if (await sheets.ask({ title: t('look.dropOwn'), ok: t('look.dropOwn'), cancel: t('common.cancel'), danger: true })) void work(() => api.deleteMyPhoto(), () => t('look.photoGone'));
}
export function photoItems(): MenuItem[] {
  const me = session.me;
  if (!me) return [];
  const { telegram, own } = me.photo;
  return [
    { label: t('look.fromTg'), checked: telegram, onselect: () => { if (!telegram) void work(() => api.updateMe({ avatarTg: true }), () => t('look.tgOn')); } },
    ...(own ? [{ label: t('look.own'), checked: !telegram, onselect: () => { if (telegram) void work(() => api.updateMe({ avatarTg: false }), () => t('look.photoSet')); } }] : []),
    // instant: the file picker opens inside the tap itself (iOS opens none from a later task)
    { label: t('look.upload'), instant: true, onselect: pick },
    ...(own ? [{ label: t('look.dropOwn'), destructive: true, onselect: () => void dropOwn() }] : []),
  ];
}

// ---- the nick: lists and feeds show it instead of my name, my profile shows both (the nick rule, Nov 2) ----
export async function editNick() {
  const now = session.me?.nick ?? '';
  const v = await sheets.askText({ title: t('look.nick'), placeholder: t('look.nickPh'), max: 24, line: true, value: now, ok: t('common.save'), cancel: t('common.cancel') });
  if (v != null && v !== now) setNick(v);
}
export const setNick = (v: string | null) => void work(() => api.updateMe({ nick: v }), (m) => t(m.nick ? 'look.nickSet' : 'look.nickOff'));

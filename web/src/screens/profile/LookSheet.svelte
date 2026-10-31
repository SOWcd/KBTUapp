<script lang="ts">
  // My nickname and photo (SPEC §3). The photo: "Photo from Telegram" (on: it refreshes by itself on every
  // open) or my own; uploading one turns the switch off, turning it on goes back to Telegram's (mine is kept for later).
  // The nick: everyone sees it; organizers see my real name beside it (the door, attendees, the club's team, DMP).
  import { untrack } from 'svelte';
  import Camera from '@lucide/svelte/icons/camera';
  import X from '@lucide/svelte/icons/x';
  import { api, ApiErr, type Me } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { skinOf, skinned, STRAP, banded, type Look } from '../../lib/awards';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import { byRank } from '../../lib/perms';

  let { overlay }: { overlay: Overlay } = $props();
  const me = $derived(session.me!);
  const real = $derived(me.student ? `${me.student.firstName} ${me.student.lastName.slice(0, 1)}.` : me.tg.firstName);
  let nick = $state(untrack(() => session.me?.nick ?? ''));
  let busy = $state<'' | 'photo' | 'tg' | 'nick' | 'skin'>('');
  // badges as skins: KBTU's, or that of a club I'm in that has one. In order of weight (owner, Oct 13:
  // "no chaos"): my own first, then my clubs by my role in them, KBTU's, the standard one, last
  const mine = $derived([...me.memberships].sort(byRank).map((m) => m.org).filter(skinned));
  // then every other club's, to try on
  const skins = $derived([...mine, ...data.orgs.filter((o) => skinned(o) && !mine.some((x) => x.id === o.id))]);
  async function pickSkin(id: number | 'sower' | null) {
    if (busy || id === me.skin) return;
    // no toast (owner, Oct 29: "Lanyard" popping up on every pick looked cheap): the badge above changes at once and
    // swings in (Hero); a failure puts the old one back
    const was = me;
    busy = 'skin';
    session.me = { ...me, skin: id };
    try { session.me = await api.updateMe({ skin: id }); } catch (e) { session.me = was; oops(e); } finally { busy = ''; }
  }
  let file = $state<HTMLInputElement>();

  function done(m: Me, msg: string) { session.me = m; haptic.ok(); say(msg, 'sparkles_3d'); }
  function oops(e: unknown) {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'nick' ? t('look.badNick') : e instanceof ApiErr && e.message === 'not_an_image' ? t('look.badPhoto') : t('common.error'), 'pleading_face_3d');
  }
  async function upload(f: File | undefined) {
    if (!f || busy) return;
    busy = 'photo';
    try { done(await api.uploadMyPhoto(f), t('look.photoSet')); } catch (e) { oops(e); } finally { busy = ''; if (file) file.value = ''; }
  }
  async function switchTg(box: HTMLInputElement) {
    const on = box.checked;
    if (!on && !me.photo.own) { box.checked = true; file?.click(); return; } // off means my own photo: pick one first
    busy = 'tg';
    try { done(await api.updateMe({ avatarTg: on }), on ? t('look.tgOn') : t('look.photoSet')); }
    catch (e) { box.checked = me.photo.telegram; oops(e); } finally { busy = ''; }
  }
  async function dropPhoto() {
    if (busy) return;
    busy = 'photo';
    try { done(await api.deleteMyPhoto(), t('look.photoGone')); } catch (e) { oops(e); } finally { busy = ''; }
  }
  function clearNick() { nick = ''; void saveNick(); }
  async function saveNick() {
    if (busy || nick.trim() === (me.nick ?? '')) return;
    busy = 'nick';
    try { const m = await api.updateMe({ nick: nick.trim() || null }); nick = m.nick ?? ''; done(m, m.nick ? t('look.nickSet') : t('look.nickOff')); }
    catch (e) { oops(e); } finally { busy = ''; }
  }
</script>

<!-- under my lanyard, which stays in sight above and changes as I pick: so no big photo here -->
<Sheet {overlay} see title={t('look.title')}>
  {#if session.me}
  <input bind:this={file} type="file" accept="image/*" hidden onchange={(e) => upload(e.currentTarget.files?.[0])} />
  <!-- one block: a square "other photo" on the left (my own photo in it once I have one), the switch
       on the right -->
  <div class="photo">
    <button class="sq" class:own={!!me.photo.own} class:busy={busy === 'photo'} disabled={!!busy} onclick={() => file?.click()} style={me.photo.own ? `background-image:url(${me.photo.own})` : ''}>
      {#if !me.photo.own}<Camera size={22} />{/if}<i>{me.photo.own ? t('look.change') : t('look.other')}</i></button>
    {#if me.photo.own}<button class="drop" disabled={!!busy} onclick={dropPhoto} aria-label={t('look.dropPhoto')}><X size={14} /></button>{/if}
    <label class="switch">
      <span><b>{t('look.tg')}</b><i class="t-foot">{t('look.tgHint')}</i></span>
      <input type="checkbox" role="switch" checked={me.photo.telegram} disabled={!!busy} onchange={(e) => switchTg(e.currentTarget)} />
    </label>
  </div>

  {#if skins.length || me.founder}
    <h3 class="t-cap cap">{t('look.skin')}</h3>
    <!-- each lanyard drawn small, as it hangs on the profile (names alone said nothing; with many clubs
         the row scrolls) -->
    <div class="skins" role="radiogroup" aria-label={t('look.skin')}>
      {#each [...(me.founder ? [{ id: 'sower' as const, kind: 'sower', name: 'SOWER', word: 'SOWER' }] : []),
              ...skins.map((o) => ({ id: o.id, kind: skinOf(o)!, name: o.name, word: STRAP[skinOf(o)!] })),
              { id: null, kind: 'kbtu', name: 'KBTU', word: 'KBTU' }] as k (k.id ?? 'kbtu')}
        <button class="ly {k.kind}" role="radio" aria-checked={me.skin === k.id} class:on={me.skin === k.id} disabled={!!busy} onclick={() => { haptic.select(); void pickSkin(k.id); }}>
          <span class="st"><i>{k.word}</i></span><span class="cl"></span>
          <span class="cd">{#if banded(k.kind as Look)}<span class="mini"><LanyardBand look={k.kind as Look} wide /></span>{/if}<span class="ph"></span><span class="ln"></span><span class="ln s"></span><span class="hl"></span></span>
          <b class="ellipsis">{k.name}</b>
        </button>
      {/each}
    </div>
  {/if}

  <h3 class="t-cap cap">{t('look.nick')}</h3>
  <label class="field nick"><input bind:value={nick} maxlength="24" aria-label={t('look.nick')} placeholder={t('look.nickPh')} enterkeyhint="done" autocomplete="off"
    onkeydown={(e) => { if (e.key === 'Enter') { e.currentTarget.blur(); void saveNick(); } }} />
    {#if me.nick}<button class="x" onclick={clearNick} disabled={!!busy} aria-label={t('look.dropNick')}><X size={16} /></button>{/if}</label>
  <p class="t-foot hint">{t('look.nickHint', { name: real })}</p>
  {/if}

  {#snippet footer()}
    {#if session.me}<Button kind="primary" size="l" full loading={busy === 'nick'} disabled={nick.trim() === (me.nick ?? '')} onclick={saveNick}>{t('look.saveNick')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .photo { position: relative; display: flex; gap: 8px; margin: 4px 0 0; }
  .photo .switch { flex: 1; min-width: 0; }
  .sq { flex: none; width: 84px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; border-radius: var(--r-m);
    background: var(--surface-2) center / cover; color: var(--accent-text); transition: transform var(--t-fast) var(--ease); }
  .sq:active { transform: scale(0.95); }
  .sq i { font: 620 12px/1.15 var(--font-text); font-style: normal; text-align: center; padding: 0 4px; }
  /* over my photo the caption sits on a dark strip at the bottom */
  .sq.own { justify-content: flex-end; overflow: hidden; }
  .sq.own i { width: 100%; padding: 5px 4px; background: rgba(0, 0, 0, 0.5); color: #fff; }
  .sq.busy { animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  .drop { position: absolute; left: 66px; top: -6px; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--danger); color: #fff; box-shadow: 0 0 0 2px var(--bg); }
  .nick { flex-direction: row; align-items: center; }
  .x { flex: none; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface); color: var(--text-2); }
  .cap { margin: 18px 2px 8px; }
  .hint { margin: 8px 2px 0; text-wrap: pretty; }
  /* the lanyards, small: strap, clip and card in each one's colours (Hero.svelte's, scaled down) */
  .skins { display: flex; gap: 10px; overflow-x: auto; margin: 0 calc(-1 * var(--gutter)); padding: 4px var(--gutter) 6px; scrollbar-width: none; }
  .skins::-webkit-scrollbar { display: none; }
  .ly .mini :global(*) { animation: none !important; } /* swatches stay still: many full lanyards at once */
  .ly { flex: none; width: 92px; display: flex; flex-direction: column; align-items: center; padding: 8px 6px 8px; border-radius: 16px; background: var(--surface-2);
    box-shadow: inset 0 0 0 2px transparent; transition: box-shadow var(--t-fast), transform var(--t-fast) var(--ease); }
  .ly:active { transform: scale(0.95); }
  .ly.on { box-shadow: inset 0 0 0 2px var(--accent); }
  .ly .st { width: 12px; height: 26px; display: flex; justify-content: center; overflow: hidden; background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); }
  .ly .st i { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 4.5px/12px var(--font-text); font-style: normal; letter-spacing: 0.2em; color: rgba(255, 255, 255, 0.85); white-space: nowrap; }
  .ly .cl { width: 18px; height: 7px; margin-bottom: -4px; z-index: 1; border-radius: 3px; background: linear-gradient(180deg, #F4F6FB, #9AA4B8); }
  .ly .cd { position: relative; width: 74px; height: 48px; padding: 9px 7px 6px; border-radius: 9px; display: grid; grid-template-columns: 16px 1fr; grid-template-rows: 6px 6px 1fr; gap: 3px 5px; overflow: hidden;
    background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(155deg, #2A4FD6, #121A3D 72%); }
  .ly .ph { grid-row: 1 / 3; width: 16px; height: 16px; border-radius: 5px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln { height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln.s { width: 60%; opacity: 0.6; }
  .ly .hl { grid-column: 1 / 3; align-self: end; height: 7px; border-radius: 3px; background: linear-gradient(100deg, #FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A); }
  .ly b { max-width: 100%; margin-top: 7px; font: 620 12px/1.2 var(--font-text); }
  .ly .ph { z-index: 1; }
  .ly .ln, .ly .hl { position: relative; z-index: 1; }
  /* the club's real card art, the profile's (LanyardBand wide) shrunk to the swatch: 340 px wide -> 74 */
  .mini { position: absolute; left: 0; top: 0; width: 340px; height: 221px; transform: scale(0.2176); transform-origin: 0 0; pointer-events: none; }
  .ly.studex .st { background: linear-gradient(90deg, #A9271E, #CF3428 50%, #A9271E); }
  .ly.studex .hl { background: #fff; }
  .ly.cheer .st { background: linear-gradient(90deg, #1E2140, #3A3F72 50%, #1E2140); }
  .ly.cheer .hl { background: linear-gradient(100deg, #FFE7A3, #FFC6E0, #FFE7A3); }
  .ly.knights .st { background: linear-gradient(90deg, #163E7C, #2F6BD0 50%, #163E7C); }
  .ly.knights .hl { background: linear-gradient(90deg, #1C4C94, #2F6BD0); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35); }
  .ly.moments .st { background: linear-gradient(90deg, #7A321F, #B5603F 50%, #7A321F); }
  .ly.moments .st i { color: #F4D9BE; }
  .ly.moments .hl { background: linear-gradient(100deg, #F2DEC8, #E3A985, #C9C391); }
  .ly.faces .st { background: linear-gradient(90deg, rgba(0, 0, 0, 0.3), transparent 35% 65%, rgba(0, 0, 0, 0.3)), linear-gradient(180deg, #6E7BFF, #C04BFF 55%, #FF4F9A); } /* shaded round like the others */
  .ly.faces .hl { background: linear-gradient(100deg, #6E7BFF, #C04BFF, #FF4F9A, #FFA43D); }
  .ly.sower .st { background: linear-gradient(90deg, #DCDCE0, #fff 50%, #DCDCE0); }
  .ly.sower .st i { color: #000; }
  .ly.sower .cd { background: radial-gradient(90% 120% at 0% 0%, #26262B, #000 62%); }
  .ly.sower .cd::before { content: ''; position: absolute; right: -30px; top: -30px; width: 76px; height: 76px; border-radius: 50%;
    background: repeating-radial-gradient(circle, transparent 0 5px, rgba(255, 255, 255, 0.14) 5px 5.6px); }
  .ly.sower .hl { background: #fff; }
</style>

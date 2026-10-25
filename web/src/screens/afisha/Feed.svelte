<script lang="ts">
  // Events → Feed: full-screen posters, one per event, vertical snap. Perf rules from the prototype:
  // no backdrop-filter inside slides (tinted solid buttons instead), the slow zoom runs only on the
  // slide on screen (IntersectionObserver), images decode async.
  import Plus from '@lucide/svelte/icons/plus';
  import Check from '@lucide/svelte/icons/check';
  import Bell from '@lucide/svelte/icons/bell';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import Share from '@lucide/svelte/icons/share';
  import Volume2 from '@lucide/svelte/icons/volume-2';
  import VolumeX from '@lucide/svelte/icons/volume-x';
  import { onMount } from 'svelte';
  import { data, phrase, prefetchEvent, toggleGoing, toggleSaved } from '../../lib/state/data.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { focusPos } from '../../lib/photo';
  import { sheets } from '../../lib/state/sheets';
  import { t, fmtNum, money, friendsLine, placeOf } from '../../lib/i18n/index.svelte';
  import { whenLine } from '../../lib/time';
  import { openLink, shareCard, haptic } from '../../lib/tg';
  import Emoji from '../../ui/Emoji.svelte';
  import OrgTag from '../../ui/OrgTag.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { feedTint } from '../../ui/chrome';
  import { ui, overlays } from '../../lib/state/ui.svelte';

  const list = $derived(data.events.filter((e) => e.status !== 'cancelled'));
  let root: HTMLDivElement;
  let cur = $state(0);

  // nav and capsule over the Feed take the tint of the slide on screen ('#RRGGBB' → 'r g b')
  $effect(() => {
    const hex = cur >= list.length ? '#1A1440' : list[cur]?.tint; // the last slide ("that's all") has its own: its violet glow on the dark
    if (!hex) return;
    const n = parseInt(hex.slice(1, 7), 16);
    feedTint(`${n >> 16} ${(n >> 8) & 255} ${n & 255}`);
  });

  onMount(() => {
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) if (en.isIntersecting) cur = Number((en.target as HTMLElement).dataset.i);
    }, { root, threshold: 0.6 });
    const watch = () => root.querySelectorAll('.slide').forEach((s) => io.observe(s));
    watch();
    const mo = new MutationObserver(watch);
    mo.observe(root, { childList: true });
    return () => { io.disconnect(); mo.disconnect(); };
  });

  // an event's video plays on the slide on screen, muted as in every feed, and loops; the next and the previous one
  // load ahead, the rest are their poster only. The sound, once turned on, stays on for the following videos.
  let sound = $state(false);
  const pic: Record<number, number> = $state({}); // which photo of a slide's strip is on screen
  // only while the Feed is what's on screen: not under a sheet, not from another page or tab
  const shown = $derived(ui.tab === 'afisha' && ui.page.afisha === 0 && !overlays.length);
  function playing(el: HTMLVideoElement, on: boolean) {
    const set = (o: boolean) => { if (o) el.play().catch(() => {}); else { el.pause(); el.currentTime = 0; } };
    set(on);
    return { update: set };
  }

  // our bot's card with a button, as from the event sheet (never a bare link: owner, Oct 4)
  function share(id: number, title: string) {
    haptic.tap();
    shareCard({ kind: 'ev', id: String(id) }, 'https://t.me/KBTUappBot?startapp=ev_' + id, title)
      .then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'pleading_face_3d'); });
  }
</script>

<div class="feed" bind:this={root}>
  {#each list as e, i (e.id)}
    {@const st = e.my?.status}
    {@const full = e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold'}
    <div class="slide" class:cur={i === cur} data-i={i} style="--tint:{e.tint}" role="button" tabindex="0"
         onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => { if (!(ev.target as HTMLElement).closest('.side')) sheets.event(e.id); }} onkeydown={(k) => k.key === 'Enter' && sheets.event(e.id)}>
      <div class="bg">
        {#if e.video?.url && Math.abs(i - cur) <= 1}
          <video src={e.video.url} poster={e.video.poster?.url} muted={!sound} loop playsinline preload="auto" use:playing={i === cur && shown}></video>
        {:else if e.video?.poster}<img src={e.video.poster.url} alt="" decoding="async" loading="lazy" class="still" />
        {:else if e.cover && e.slides?.length}
          <!-- the cover and its photos, swiped sideways like a TikTok photo post (PLAN 33); at the last one the swipe turns the page -->
          <div class="strip" data-edge onscroll={(s) => (pic[e.id] = Math.round(s.currentTarget.scrollLeft / s.currentTarget.clientWidth))}>
            <img src={e.cover.url} alt="" decoding="async" loading={i < 2 ? 'eager' : 'lazy'} style:object-position={focusPos(e.cover)} />
            {#each e.slides as p (p.id)}<img src={p.url} alt="" decoding="async" loading="lazy" />{/each}
          </div>
        {:else if e.cover}<img src={e.cover.url} alt="" decoding="async" loading={i < 2 ? 'eager' : 'lazy'} style:object-position={focusPos(e.cover)} />
        {:else}<span class="art"><Emoji name={e.emoji ?? 'sparkles_3d'} size={170} /></span>{/if}
      </div>
      <div class="shade"></div>

      <div class="info">
        {#if !e.video?.url && e.cover && e.slides?.length}
          <span class="dots" aria-hidden="true">{#each [e.cover, ...e.slides] as _, k (k)}<i class:on={k === (pic[e.id] ?? 0)}></i>{/each}</span>
        {/if}
        <span class="org"><OrgTag org={e.org} /></span>
        <h2 class="title">{e.title}</h2>
        <p class="meta">{whenLine(e.startsAt)} · {placeOf(e.place)}{e.price ? ' · ' + money(e.price) : ''}</p>
        {#if e.friends.length}
          <p class="fr">
            <span class="stack">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={22} tappable={false} />{/each}</span>
            {friendsLine(e.friends.map((f) => f.name))}
          </p>
        {/if}
      </div>

      <div class="side">
        {#if e.externalUrl}
          <button class="act go" onclick={() => openLink(e.externalUrl!)} aria-label={t('event.external')}><span class="ring"><Plus size={26} strokeWidth={2.4} /></span></button>
        {:else}
          <button class="act go" class:on={st === 'going'} class:wait={full || st === 'waitlist'} onclick={() => toggleGoing(e.id, () => sheets.pay(e.id))}
                  aria-label={st === 'going' ? t('event.cancelReg') : full ? t('event.notify') : t('event.go')}>
            <span class="ring">
              {#if st === 'going'}<Check size={26} strokeWidth={2.6} />{:else if full || st === 'waitlist'}<Bell size={22} strokeWidth={2.2} fill={st === 'waitlist' ? 'currentColor' : 'none'} />{:else}<Plus size={26} strokeWidth={2.4} />{/if}
            </span>
            <b class="num">{st === 'going' ? t('feed.going') : full ? t('event.full') : fmtNum(e.taken)}</b>
          </button>
        {/if}
        {#if e.video?.url}
          <button class="act" onclick={() => { sound = !sound; haptic.tap(); }} aria-label={t('feed.sound')} aria-pressed={sound}>
            <span class="ring sm">{#if sound}<Volume2 size={21} />{:else}<VolumeX size={21} />{/if}</span>
          </button>
        {/if}
        <button class="act" class:saved={e.saved} onclick={() => toggleSaved(e.id)} aria-label={t('event.save')}>
          <span class="ring sm"><Bookmark size={21} fill={e.saved ? 'currentColor' : 'none'} /></span>
        </button>
        <button class="act" onclick={() => share(e.id, e.title)} aria-label={t('event.share')}>
          <span class="ring sm"><Share size={21} /></span>
        </button>
      </div>
    </div>
  {:else}
    <p class="empty">{t('feed.empty')}</p>
  {/each}
  {#if list.length}
    <!-- the end of the Feed: a calm last slide instead of a wall -->
    <div class="slide end" class:cur={cur === list.length} data-i={list.length}>
      <span class="endart"><Emoji name="sparkles_3d" size={96} /></span>
      <b>{t('feed.end')}</b>
      <p>{t('feed.endText')}</p>
      <span class="endacts"><button onclick={() => (ui.page.afisha = 1)}>{t('page.list')}</button><button onclick={() => { ui.tab = 'club'; ui.page.club = 0; }}>{t('page.clubs')}</button></span>
    </div>
  {/if}
</div>

<style>
  .feed { position: absolute; inset: 0; overflow-y: auto; scroll-snap-type: y mandatory; overscroll-behavior: contain; scrollbar-width: none; background: #000; }
  .feed::-webkit-scrollbar { display: none; }
  /* the slide is role=button and :active reaches it from every rail button inside, so base.css's press give scaled the
     whole screen to .965 at each Going / Save / Share and the Feed re-snapped 12 px (B3's jump, PLAN 81): it never gives */
  .slide { position: relative; height: 100%; scroll-snap-align: start; scroll-snap-stop: always; overflow: hidden; color: #fff; background: var(--tint); transform: none; opacity: 1; }
  .bg { position: absolute; inset: 0; }
  .bg img { width: 100%; height: 100%; object-fit: cover; transform: scale(1.06); }
  .bg video, .bg .still { width: 100%; height: 100%; object-fit: cover; transform: none; }
  .cur .bg > img:not(.still) { animation: kb 14s ease-in-out infinite alternate; }
  .strip { display: flex; height: 100%; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain; scrollbar-width: none; }
  .strip::-webkit-scrollbar { display: none; }
  .strip img { flex: 0 0 100%; scroll-snap-align: start; scroll-snap-stop: always; transform: none; }
  .dots { display: flex; gap: 5px; align-self: center; }
  .dots i { width: 6px; height: 6px; border-radius: 50%; background: rgba(255, 255, 255, 0.45); transition: background-color var(--t-fast), transform var(--t-fast); }
  .dots i.on { background: #fff; transform: scale(1.25); }
  .art { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding-bottom: 18vh;
    background: radial-gradient(90% 60% at 50% 30%, rgba(255, 255, 255, 0.22), transparent 60%), var(--tint); }
  .cur .art :global(img) { animation: float 5s ease-in-out infinite alternate; }
  .shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0, 0, 0, 0.45) 0%, transparent 22%, transparent 45%, rgba(0, 0, 0, 0.78) 82%); }

  .info { position: absolute; left: var(--gutter); right: 84px; bottom: calc(var(--bottom) + 8px); display: flex; flex-direction: column; gap: 8px; }
  .org { align-self: flex-start; display: flex; max-width: 100%; }
  .title { font: 800 29px/1.04 var(--font-display); letter-spacing: -0.035em; text-wrap: balance; text-shadow: 0 2px 18px rgba(0, 0, 0, 0.35); }
  .meta { font: 550 14px/1.35 var(--font-text); color: rgba(255, 255, 255, 0.86); }
  .fr { display: flex; align-items: center; gap: 8px; font: 600 13.5px/1.3 var(--font-text); }
  .stack { display: flex; }
  .stack :global(.av + .av) { margin-left: -7px; }
  .stack :global(.av) { box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.5); }

  .side { position: absolute; right: 12px; bottom: calc(var(--bottom) + 8px); display: flex; flex-direction: column; align-items: center; gap: 14px; }
  .act { display: flex; flex-direction: column; align-items: center; gap: 5px; color: #fff; }
  /* a press on a ring never pans the Feed (B3, video); the labels still swipe (review: the whole column was dead) */
  .ring { touch-action: none; width: 58px; height: 58px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: rgba(20, 22, 32, 0.42); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16); transition: transform var(--t-fast) var(--ease), background-color var(--t-base) var(--ease), color var(--t-base); }
  .ring.sm { width: 48px; height: 48px; }
  .act:active .ring { transform: scale(0.9); }
  .go .ring { background: var(--accent); box-shadow: 0 10px 26px -8px rgba(59, 107, 255, 0.9); }
  .go.on .ring { background: #fff; color: var(--accent); }
  .go.wait .ring { background: rgba(20, 22, 32, 0.42); }
  .act b { font: 700 12.5px/1 var(--font-text); text-shadow: 0 1px 8px rgba(0, 0, 0, 0.5); }
  .saved .ring { color: #FFD23F; }

  .end { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 0 32px calc(var(--bottom) + 40px); text-align: center;
    background: radial-gradient(80% 50% at 50% 35%, rgba(124, 77, 255, 0.35), transparent 70%), #07080F; }
  .end b { font: 800 26px/1.1 var(--font-display); letter-spacing: -0.03em; }
  .end p { font: 500 15px/1.45 var(--font-text); color: rgba(255, 255, 255, 0.72); text-wrap: balance; }
  .endart { margin-bottom: 6px; }
  .cur .endart :global(img) { animation: float 5s ease-in-out infinite alternate; }
  .endacts { display: flex; gap: 10px; margin-top: 10px; }
  .endacts button { height: 44px; padding: 0 20px; border-radius: var(--r-full); background: rgba(255, 255, 255, 0.12); color: #fff; font: 650 15px/1 var(--font-text);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14); }
  .endacts button:active { transform: scale(0.96); }
  .empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: rgba(255, 255, 255, 0.7); padding: 40px; text-align: center; }
  :global(html.lowfx) .cur .bg img, :global(html.lowfx) .cur .art :global(img), :global(html.lowfx) .cur .endart :global(img) { animation: none; } /* power saving */
  @keyframes kb { from { transform: scale(1.06) translate3d(0, 0, 0); } to { transform: scale(1.16) translate3d(-2%, -1.5%, 0); } }
  @keyframes float { from { transform: translate3d(0, -6px, 0) rotate(-3deg); } to { transform: translate3d(0, 8px, 0) rotate(3deg); } }
</style>

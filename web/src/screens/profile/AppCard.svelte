<script lang="ts">
  // The app itself (mockup v24: three tiles, small actions): its channel, its group, support for the project (the open
  // code without a number), and "Support & ideas": the creator and the main admin, faces and all (owner, Nov 6).
  // At the bottom of Me (not on Settings).
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Avatar from '../../ui/Avatar.svelte';
  import { writeOwner, OWNER } from '../../lib/feedback';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';

  // the app's own Telegram: news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop';
  const support = $derived(session.support);
  const write = (u: string) => { haptic.tap(); openLink(`https://t.me/${u}?text=${encodeURIComponent(t('fb.draft'))}`); };
</script>

<!-- v25: three cards, not rows, but grown-up: the brand's small solid tile, the name, one line under
     it; the group is a forum with topics, so it says so. No "found a bug" line -->
<div class="appc surface" data-away><!-- data-away: it leaves while Me's settings are open -->
  <div class="ap-h"><span class="mk"><KbtuMark size={20} /></span><b>KBTU App</b></div>
  <div class="ap-t">
    <button class="apt" onclick={() => openLink(TG_NEWS)}><span class="ic" style="--c:#2AABEE"><Megaphone size={17} /></span>
      <b>{t('app.channel')}</b><small>{t('app.channelSub')}</small><ArrowUpRight class="go" size={14} /></button>
    <button class="apt" onclick={() => openLink(TG_TALK)}><span class="ic" style="--c:#7C5CFF"><MessagesSquare size={17} /></span>
      <b>{t('app.group')}</b><small>{t('app.groupSub')}</small><ArrowUpRight class="go" size={14} /></button>
    {#if session.donate}
      <button class="apt" onclick={() => { haptic.tap(); sheets.settings('donate'); }}><span class="ic" style="--c:var(--accent)"><HandHeart size={17} /></span>
        <b>{t('app.donate')}</b><small>{t('app.donateSub')}</small></button>
    {:else}
      <button class="apt" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><span class="ic gh"><GitHubMark size={17} /></span>
        <b>GitHub</b><small>{t('app.codeSub')}</small><ArrowUpRight class="go" size={14} /></button>
    {/if}
  </div>
  {#if support.length}
    <!-- one way to us: two faces, each a tap to their Telegram with a draft that says it's from the app -->
    <p class="sp-h">{t('app.support')}</p>
    <div class="sp">
      {#each support as p (p.id)}
        <button class="who" onclick={() => write(p.username)}>
          <Avatar person={p} size={36} tappable={false} />
          <span class="wt"><b class="ellipsis">{p.realName ?? p.name}</b><small>{p.founder ? t('app.creator') : t('app.mainAdmin')}</small></span>
          <TelegramMark size={16} />
        </button>
      {/each}
    </div>
  {:else}
    <button class="write" onclick={writeOwner}><TelegramMark size={17} /><span class="wl">{t('fb.write')}</span><b>@{OWNER}</b></button>
  {/if}
</div>

<style>
  .appc { display: flex; flex-direction: column; gap: 10px; padding: 14px 12px 12px; border-radius: var(--r-l); }
  .ap-h { display: flex; gap: 10px; align-items: center; padding: 0 4px 2px; }
  .ap-h b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .mk { flex: none; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); }
  .ap-t { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  /* plain tiles, glossy icons (the glass tile was too much) */
  .apt { position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: flex-start; padding: 12px 10px 11px 12px; border-radius: 18px; text-align: left; color: var(--text-3); background: var(--surface-2); }
  .apt:active { transform: scale(0.97); }
  .ic { display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; margin-bottom: 10px; border-radius: 11px; color: #fff;
    background: linear-gradient(160deg, color-mix(in srgb, var(--c) 62%, #fff), var(--c) 52%, color-mix(in srgb, var(--c) 78%, #000));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), inset 0 -2px 4px rgba(0, 0, 0, 0.18), 0 8px 16px -8px var(--c); }
  .ic.gh { --c: #3A4048; }
  .apt b { font: 650 var(--fs-body)/1.15 var(--font-text); color: var(--text); }
  .apt small { margin-top: 2px; font: 500 var(--fs-cap)/1.25 var(--font-text); color: var(--text-3); }
  .apt :global(.go) { position: absolute; top: 12px; right: 10px; }
  .write { display: flex; align-items: center; gap: 10px; height: 46px; padding: 0 16px; border-radius: var(--r-full);
    background: color-mix(in srgb, #2AABEE 14%, transparent); color: #2AABEE; }
  .wl { flex: 1; text-align: left; font: 650 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .write b { font: 650 var(--fs-sub)/1 var(--font-text); }
  .write:active { transform: scale(0.98); }
  .sp-h { margin: 4px 4px -2px; font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .sp { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .who { display: flex; align-items: center; gap: 10px; min-width: 0; padding: 10px 12px 10px 10px; border-radius: var(--r-m); background: var(--surface-2); color: var(--accent); text-align: left; }
  .who:active { transform: scale(0.97); }
  .wt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .wt b { font: 600 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .wt small { font: 500 var(--fs-cap)/1.25 var(--font-text); color: var(--text-3); }
  :global(:root[data-theme='light']) .write { color: #0F6E9F; } /* 4.9:1 on the tint */
</style>

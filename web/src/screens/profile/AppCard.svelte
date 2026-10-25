<script lang="ts">
  // The app itself (mockup v24: three tiles, small actions): its channel, its group, the open code (owner, Oct 17), and
  // a word straight to the creator (owner, Oct 5). At the bottom of Me (owner, Oct 25: not on Settings).
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { openLink } from '../../lib/tg';
  import { writeOwner, OWNER } from '../../lib/feedback';

  // the app's own Telegram (owner, Oct 5): news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop';
</script>

<!-- v25 (owner, Oct 25): three cards, not rows, but grown-up: the brand's small solid tile, the name, one line under
     it; the group is a forum with topics, so it says so. No "found a bug" line (owner) -->
<div class="appc surface">
  <div class="ap-h"><span class="mk"><KbtuMark size={20} /></span><b>KBTU App</b></div>
  <div class="ap-t">
    <button class="apt" onclick={() => openLink(TG_NEWS)}><span class="ic" style="--c:#2AABEE"><Megaphone size={17} /></span>
      <b>{t('app.channel')}</b><small>{t('app.channelSub')}</small><ArrowUpRight class="go" size={14} /></button>
    <button class="apt" onclick={() => openLink(TG_TALK)}><span class="ic" style="--c:#7C5CFF"><MessagesSquare size={17} /></span>
      <b>{t('app.group')}</b><small>{t('app.groupSub')}</small><ArrowUpRight class="go" size={14} /></button>
    <button class="apt" onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><span class="ic gh"><GitHubMark size={17} /></span>
      <b>GitHub</b><small>{t('app.codeSub')}</small><ArrowUpRight class="go" size={14} /></button>
  </div>
  <!-- a word straight to the creator: its own long pill, his @username on it (owner, Oct 21) -->
  <button class="write" onclick={writeOwner}><TelegramMark size={17} /><span class="wl">{t('fb.write')}</span><b>@{OWNER}</b></button>
</div>

<style>
  .appc { display: flex; flex-direction: column; gap: 10px; padding: 14px 12px 12px; border-radius: var(--r-l); }
  .ap-h { display: flex; gap: 10px; align-items: center; padding: 0 4px 2px; }
  .ap-h b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .mk { flex: none; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 10px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); }
  .ap-t { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .apt { position: relative; display: flex; flex-direction: column; align-items: flex-start; padding: 12px 10px 11px 12px; border-radius: 16px; text-align: left;
    background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); color: var(--text-3); }
  .apt:active { transform: scale(0.97); }
  .ic { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; margin-bottom: 10px; border-radius: 10px; color: #fff; background: var(--c); }
  .ic.gh { background: #24292F; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14); }
  .apt b { font: 650 var(--fs-body)/1.15 var(--font-text); color: var(--text); }
  .apt small { margin-top: 2px; font: 500 var(--fs-cap)/1.25 var(--font-text); color: var(--text-3); }
  .apt :global(.go) { position: absolute; top: 12px; right: 10px; }
  .write { display: flex; align-items: center; gap: 10px; height: 46px; padding: 0 16px; border-radius: var(--r-full);
    background: color-mix(in srgb, #2AABEE 14%, transparent); color: #2AABEE; }
  .wl { flex: 1; text-align: left; font: 650 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .write b { font: 650 var(--fs-sub)/1 var(--font-text); }
  .write:active { transform: scale(0.98); }
  :global(:root[data-theme='light']) .write { color: #0F6E9F; } /* 4.9:1 on the tint */
</style>

<script lang="ts">
  // The app itself (mockup v24: three tiles, small actions): its channel, its group, the open code (owner, Oct 17), and
  // a word straight to the creator (owner, Oct 5). At the bottom of Me (owner, Oct 25: not on Settings).
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import GitHubMark from '../../ui/GitHubMark.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { glass } from '../../ui/glass';
  import { t } from '../../lib/i18n/index.svelte';
  import { openLink } from '../../lib/tg';
  import { writeOwner, OWNER } from '../../lib/feedback';

  // the app's own Telegram (owner, Oct 5): news in the channel, talk in the topics group (BUGS / IDEAS / QUESTIONS)
  const TG_NEWS = 'https://t.me/KBTUappNews', TG_TALK = 'https://t.me/KBTUappTop';
</script>

<div class="appc surface">
  <div class="ap-h"><span class="mk"><KbtuMark size={22} /></span><span><b>KBTU App</b><i class="sub">{t('fb.text')}</i></span></div>
  <div class="ap-t">
    <button class="apt" use:glass={{ bloom: true }} onclick={() => openLink(TG_NEWS)}><Megaphone size={22} /><b>{t('app.channel')}</b><small>{t('app.channelSub')}</small><span class="go">{t('app.subscribe')}</span></button>
    <button class="apt" use:glass={{ bloom: true }} onclick={() => openLink(TG_TALK)}><UsersRound size={22} /><b>{t('app.group')}</b><small>{t('app.groupSub')}</small><span class="go">{t('app.join')}</span></button>
    <button class="apt" use:glass={{ bloom: true }} onclick={() => openLink('https://github.com/SOWcd/KBTUapp')}><GitHubMark size={22} /><b>GitHub</b><small>{t('app.codeSub')}</small><span class="go">{t('app.look')}</span></button>
  </div>
  <!-- a word straight to the creator: its own long pill, his @username on it (owner, Oct 21) -->
  <button class="write" use:glass={{ bloom: true }} onclick={writeOwner}><TelegramMark size={18} /><span>{t('fb.write')}</span><b>@{OWNER}</b></button>
</div>

<style>
  .sub { display: block; margin-top: 2px; font: 500 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .appc { display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: var(--r-l); }
  .ap-h { display: flex; gap: 12px; align-items: center; }
  .ap-h b { font: 700 var(--fs-card)/1.2 var(--font-text); }
  .mk { flex: none; display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 13px; color: #fff; background: linear-gradient(135deg, #2A4FD6, #5B2BC0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25); }
  .ap-t { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  @media (max-width: 359px) { .apt .go { display: none; } } /* a 320-px phone: the tile is the button, "Subscribe" doesn't fit */
  /* glass tiles (mockup v14): no live blur (they scroll), a lit sheen that follows the phone's tilt (glass.ts) and a
     gradient rim, bright at the top */
  .apt { position: relative; isolation: isolate; overflow: hidden; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 12px 10px 10px;
    border-radius: 16px; text-align: left; color: var(--accent-text); background: linear-gradient(160deg, color-mix(in srgb, var(--text) 9%, transparent), color-mix(in srgb, var(--text) 3%, transparent));
    box-shadow: 0 10px 22px -16px rgba(0, 0, 0, 0.6); }
  .apt::before, .write::before { content: ''; position: absolute; inset: 0; z-index: -1; border-radius: inherit; pointer-events: none;
    background: radial-gradient(120% 80% at calc(30% + var(--gx, 0) * 60%) calc(-20% + var(--gy, 0) * 40%), color-mix(in srgb, #fff 16%, transparent), transparent 60%); }
  .apt::after, .write::after { content: ''; position: absolute; inset: 0; border-radius: inherit; padding: 1px; pointer-events: none;
    background: linear-gradient(170deg, rgba(255, 255, 255, 0.45), rgba(255, 255, 255, 0.06) 40%, rgba(255, 255, 255, 0.14));
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); mask-composite: exclude; }
  :global(:root[data-theme='light']) .apt::after, :global(:root[data-theme='light']) .write::after { background: linear-gradient(170deg, rgba(255, 255, 255, 0.95), rgba(11, 20, 51, 0.08) 45%, rgba(11, 20, 51, 0.12)); }
  .apt b { margin-top: 8px; font: 650 var(--fs-body)/1.15 var(--font-text); color: var(--text); }
  .apt small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .apt .go { margin-top: 8px; font: 650 var(--fs-cap)/1 var(--font-text); color: var(--accent-text); }
  .write { position: relative; isolation: isolate; overflow: hidden; display: flex; align-items: center; gap: 10px; height: 48px; padding: 0 18px; border-radius: var(--r-full);
    background: linear-gradient(160deg, color-mix(in srgb, #2AABEE 22%, transparent), color-mix(in srgb, #2AABEE 8%, transparent)); color: #2AABEE; }
  .write span { flex: 1; text-align: left; font: 650 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .write b { font: 650 var(--fs-sub)/1 var(--font-text); color: #2AABEE; }
  .write:active, .apt:active { transform: scale(0.97); }
  :global(:root[data-theme='light']) .write { color: #0F6E9F; } :global(:root[data-theme='light']) .write b { color: #0F6E9F; } /* 4.9:1 on the tint */
</style>

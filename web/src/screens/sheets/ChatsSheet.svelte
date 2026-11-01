<script lang="ts">
  // Every chat in the directory (SPEC §4.11), grouped by what it's for (study, reviews, admission, schools and courses,
  // clubs, hobbies; the AI sorts, staff correct in Admin), the not yet sorted last; a chat aimed at a school or a course
  // says so on its line. A tap opens it in Telegram. The same for everyone: Admin's edits live in AdminChats.
  import { CHAT_SECTIONS, type Chat } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { openChat, compact, suggestChat } from '../../lib/chats';
  import Sheet from '../../ui/Sheet.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import ChatKind from '../../ui/ChatKind.svelte';
  import { schoolShort, shortOf } from '../../lib/short';

  let { overlay, chats }: { overlay: Overlay; chats: Chat[] } = $props();
  // whom it is for, when not everyone: "SITE · year 2"
  const aim = (c: Chat) => [c.school && schoolShort(c.school), c.course && t('chats.course', { n: c.course })].filter(Boolean).join(' · ');
  const groups = $derived([...CHAT_SECTIONS, null].map((s) => [s ?? 'other', chats.filter((c) => (c.section ?? null) === s)] as const).filter(([, l]) => l.length));
</script>

<Sheet {overlay} headed icon={TelegramMark} tall title={t('chats.sheet')}>
  <h2 class="t-h2 hd">{t('chats.sheet')}</h2>
  <p class="t-foot sub">{t('chats.note')}</p>
  {#each groups as [g, items] (g)}
    <h3 class="t-cap gh">{t(`chats.sec.${g}`)}</h3>
    <div class="list surface">
      {#each items as c (c.id)}
        <div class="rw">
          <button class="row" onclick={() => void openChat(c)}>
            <span class="ci" class:sq={c.kind === 'forum'}>{#if c.photo}<img src={c.photo} alt="" />{/if}<span class="kind"><ChatKind kind={c.kind} size={18} /></span></span>
            <span class="tx"><b class="ellipsis">{c.title}</b><i>{#if c.org}<em class="who">{shortOf(c.org)}</em>{/if}{aim(c) ? aim(c) + ' · ' : ''}{t(`chats.${c.kind}`)}{c.members ? ' · ' + tn('chats.members', c.members).replace(String(c.members), compact(c.members)) : ''}</i></span>
          </button>
        </div>
      {/each}
    </div>
  {/each}
  <button class="sug" onclick={suggestChat}>{t('chats.suggest')}</button>
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .sub { margin-bottom: 14px; }
  .gh { margin: 14px 4px 8px; }
  .list { display: flex; flex-direction: column; padding: 4px 0; }
  .row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 14px; text-align: left; }
  .rw + .rw { border-top: 1px solid var(--line); }
  .row:active { background: var(--surface-2); }
  .ci { position: relative; flex: none; width: 40px; height: 40px; border-radius: 50%; background: var(--surface-2); }
  .kind { position: absolute; right: -3px; bottom: -3px; display: flex; border-radius: 50%; box-shadow: 0 0 0 2px var(--surface); }
  .sq .kind { border-radius: 32%; }
  /* the chat's own avatar; a topics group is a squircle, as Telegram draws it */
  .ci.sq { border-radius: 30%; }
  .ci img { width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 640 15px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  /* whose chat it is (PLAN 86): the club's or school's short name */
  .who { margin-right: 6px; padding: 1px 6px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 11.5px/1.4 var(--font-text); font-style: normal; }
  .sug { display: block; width: 100%; height: 44px; margin-top: 14px; border-radius: var(--r-m); background: var(--surface-2); color: var(--accent-text); font: 620 14.5px/1 var(--font-text); }
</style>

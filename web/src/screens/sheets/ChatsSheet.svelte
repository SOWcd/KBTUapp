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
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { schoolShort, shortOf } from '../../lib/short';

  let { overlay, chats }: { overlay: Overlay; chats: Chat[] } = $props();
  // whom it is for, when not everyone: "SITE · year 2"
  const aim = (c: Chat) => [c.school && schoolShort(c.school), c.course && t('chats.course', { n: c.course })].filter(Boolean).join(' · ');
  const groups = $derived([...CHAT_SECTIONS, null].map((s) => [s ?? 'other', chats.filter((c) => (c.section ?? null) === s)] as const).filter(([, l]) => l.length));
</script>

<Sheet {overlay} icon={TelegramMark} tall title={t('chats.sheet')}>
  <p class="t-foot">{t('chats.note')}</p>
  <div class="groups">
    {#each groups as [g, items] (g)}
      <Group caption={t(`chats.sec.${g}`)}>
        {#each items as c (c.id)}
          <!-- whose chat it is (PLAN 86): the club's or school's short name leads its line -->
          <Row dense title={c.title} subtitle={[c.org && shortOf(c.org), aim(c), t(`chats.${c.kind}`), c.members ? tn('chats.members', c.members).replace(String(c.members), compact(c.members)) : ''].filter(Boolean).join(' · ')}
            accessory="external" onclick={() => void openChat(c)}>
            {#snippet lead()}<ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={40} />{/snippet}
          </Row>
        {/each}
      </Group>
    {/each}
    <Group><Row tone="add" title={t('chats.suggest')} onclick={suggestChat} /></Group>
  </div>
</Sheet>

<style>
  .groups { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-4); }
</style>

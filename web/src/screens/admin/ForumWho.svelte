<script lang="ts" module>
  import { t, type Key } from '../../lib/i18n/index.svelte';

  // why a forum post or reply waits for a moderator, as one line (owner, Nov 4): an appeal says so first, then the
  // verdict's own word, always; the reason the AI gave its author (ai.explain, kept on the row) after it in quotes, never
  // in its place (review: the post's words steer that model, so an injected "a false alarm" could hide the verdict)
  const WHY: Record<string, Key> = { ai: 'fc.whyAi', person: 'fc.whyPerson', check: 'fc.whyCheck', busy: 'fc.whyBusy', lost: 'fc.whyLost',
    noise: 'fc.whyNoise', ad: 'fc.whyAd', reports: 'fcr.whyReports', photo: 'fc.whyPhoto', tgno: 'fc.whyTg' };
  const AI = new Set(['ai', 'person', 'noise', 'ad']);
  export function whyLine(why: string | null | undefined, aiWhy?: string | null, reply = false): string {
    if (!why) return '';
    const word = t(reply && why === 'lost' ? 'fcr.whyLost' : WHY[why] ?? 'fc.whyCheck');
    const said = aiWhy && AI.has(why) ? `${word} · «${aiWhy}»` : word;
    return why === 'noise' || why === 'ad' ? `${t('fc.modAppeal')} · ${said}` : said; // a refusal in the queue is an appeal
  }
</script>

<script lang="ts">
  // Whose a held forum post is, for the moderator deciding on it: a named one its author's avatar and short name with
  // "Signed"; an anonymous one the mask, its random nick and "Anonymous", nothing that identifies (the server sends no
  // author for it). The owner's reveal stays behind the card's menu.
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import type { Nick, PersonRef } from '../../lib/api';
  import { nickName } from '../../lib/i18n/nicks';
  import Avatar from '../../ui/Avatar.svelte';
  import Tag from '../../ui/Tag.svelte';

  let { anon, nick, author = null }: { anon: boolean; nick: Nick; author?: PersonRef | null } = $props();
</script>

<div class="who">
  {#if anon}
    <span class="mask" aria-hidden="true"><VenetianMask size={17} strokeWidth={2} /></span>
    <b class="ellipsis">{nickName(nick) ?? t('fc.anon')}</b>
    <Tag>{t('fc.anon')}</Tag>
  {:else}
    {#if author}<Avatar person={author} size={32} />{/if}
    <b class="ellipsis">{author ? author.realName ?? author.name : '—'}</b>
    <Tag tone="accent">{t('fc.modNamed')}</Tag>
  {/if}
</div>

<style>
  .who { display: flex; align-items: center; gap: var(--s-2); min-width: 0; }
  .who b { flex: 0 1 auto; min-width: 0; font: 600 var(--fs-body)/1.25 var(--font-text); }
  .mask { flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--fill-2); color: var(--text); }
</style>

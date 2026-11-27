<script lang="ts">
  // Friends' streaks (owner, Nov 27): the streak card's faces open it. My friends and me by current weeks in a row,
  // the longest first; a row opens that person. No request of its own: the Friends page's rows carry each flame and
  // my card carries mine (both loaded with the app).
  import Flame from '@lucide/svelte/icons/flame';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import type { PersonRef } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { screenful } from '../../lib/screenful.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  type Line = { person: PersonRef; n: number; me: boolean };
  const rows = $derived.by(() => {
    const card = data.myCard;
    const now = card?.awards.achievements.find((a) => a.code === 'streak')?.now ?? 0;
    const all: Line[] = (data.friends?.friends ?? []).map((f) => ({ person: f.person, n: f.streak ?? 0, me: false }));
    if (card) all.push({ person: card, n: now, me: true });
    // the longest run first; a tie: me first among equals, then by name
    return all.sort((x, y) => y.n - x.n || +y.me - +x.me || x.person.name.localeCompare(y.person.name));
  });
  const draw = screenful(() => rows.length); // hundreds of friends: a screenful with the sheet, the rest after it paints
</script>

<Sheet {overlay} icon={Flame} title={t('streak.friends')}>
  <Group>
    {#each rows.slice(0, draw.n) as r (r.person.id)}
      <Row dense title={r.person.name} subtitle={r.me ? t('fr.isMe') : undefined} accessory="chevron" onclick={() => sheets.person(r.person.id)}>
        {#snippet lead()}<span class="av" class:me={r.me}><Avatar person={r.person} size={36} tappable={false} /></span>{/snippet}
        {#snippet detail()}
          <span class="n" class:me={r.me} class:off={!r.n}><span class="e"><Emoji name="fire_3d" size={18} /></span><b class="num">{r.n}</b></span>
        {/snippet}
      </Row>
    {/each}
  </Group>
</Sheet>

<style>
  .av { display: flex; border-radius: var(--r-full); }
  /* me among my friends: an accent ring and an accent chip */
  .av.me { box-shadow: 0 0 0 2px var(--surface-solid), 0 0 0 4px var(--accent); }
  .n { display: flex; align-items: center; gap: 4px; padding: 4px 9px 4px 7px; border-radius: var(--r-full); background: var(--fill-2); }
  .n b { font: 700 var(--fs-sub)/1 var(--font-text); }
  .n.me { background: var(--accent-soft); color: var(--accent-text); }
  .e { display: flex; }
  .n.off .e { filter: grayscale(1); opacity: 0.45; }
</style>

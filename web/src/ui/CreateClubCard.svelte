<script lang="ts">
  // Growth path (SPEC §4.6): anyone can start a club as a student initiative, official status later.
  import Plus from '@lucide/svelte/icons/plus';
  import { t } from '../lib/i18n/index.svelte';
  import { asStudent } from '../lib/state/session.svelte';
  import { sheets } from '../lib/state/sheets';
  import Emoji from './Emoji.svelte';
  import Button from './Button.svelte';

  // the application: clubs open after the creator's check (said on the sheet itself)
  const start = () => asStudent(() => sheets.createClub());
</script>

<section class="cc">
  <Emoji name="sparkles_3d" size={40} />
  <div class="txt"><b class="t-title">{t('create.title')}</b><p class="t-foot">{t('create.text')}</p></div>
  <Button kind="secondary" size="m" onclick={start}>{#snippet icon()}<Plus size={17} />{/snippet}{t('create.button')}</Button>
</section>

<style>
  .cc { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 16px; border-radius: var(--r-l); border: 1.5px dashed var(--line-2); }
  .txt { display: flex; flex-direction: column; gap: 4px; }
</style>

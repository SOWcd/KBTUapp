<script lang="ts">
  // A club's roster for DMP in a sheet (a tap on a registry row on a phone); the body is RosterBody.
  import type { OrgRef } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import BookUser from '@lucide/svelte/icons/book-user';
  import RosterBody from './RosterBody.svelte';
  let { overlay, org, onofficial }: { overlay: Overlay; org: OrgRef; onofficial?: (on: boolean) => void } = $props();
</script>

<Sheet {overlay} icon={BookUser} full title={t('cap.roster')}><RosterBody {org} {onofficial} /></Sheet>

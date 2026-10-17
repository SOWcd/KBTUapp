<script lang="ts">
  // Event or club picture: the uploaded photo, or a video's poster, or a 3D emoji on the organizer's colour. `play` (the
  // event sheet's header) with a video: the video plays over its poster, muted, with a sound button.
  import Emoji from './Emoji.svelte';
  import { focusPos } from '../lib/photo';
  import { t } from '../lib/i18n/index.svelte';
  import Volume2 from '@lucide/svelte/icons/volume-2';
  import VolumeX from '@lucide/svelte/icons/volume-x';
  type Pic = { url: string; thumb: string; focus?: [number, number] | null };
  type P = { cover: Pic | null; video?: { url: string | null; poster: Pic | null } | null; emoji: string | null; color: string | null; tint?: string };
  let { item, size = 64, radius = 14, big = false, dim = false, play = false }: { item: P; size?: number; radius?: number; big?: boolean; dim?: boolean; play?: boolean } = $props();
  const pic = $derived(item.cover ?? item.video?.poster ?? null);
  const clip = $derived(play && !dim ? item.video?.url : null);
  let sound = $state(false);
</script>

<div class="poster" class:dim style="width:{big ? '100%' : size + 'px'};height:{big ? '100%' : size + 'px'};border-radius:{radius}px;--c:{item.color ?? item.tint ?? '#3B6BFF'}">
  {#if pic}
    <!-- the big cover over the thumb the lists already loaded: the header is never empty while it comes -->
    {#if big}<img src={pic.thumb} alt="" decoding="async" style:object-position={focusPos(pic)} />{/if}
    <img src={big ? pic.url : pic.thumb} alt="" decoding="async" loading="lazy" style:object-position={focusPos(pic)} />
  {:else}
    <Emoji name={item.emoji ?? 'sparkles_3d'} size={big ? 120 : Math.round(size * 0.56)} />
  {/if}
  {#if clip}
    <video src={clip} poster={item.video?.poster?.url} autoplay muted={!sound} loop playsinline></video>
    <button class="snd" onclick={(ev) => { ev.stopPropagation(); sound = !sound; }} aria-label={t('feed.sound')} aria-pressed={sound}>
      {#if sound}<Volume2 size={18} />{:else}<VolumeX size={18} />{/if}</button>
  {/if}
</div>

<style>
  .poster {
    position: relative; flex: none; overflow: hidden; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(120% 90% at 30% 15%, rgba(255, 255, 255, 0.28), transparent 55%), var(--c);
  }
  .poster img, .poster video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .snd { position: absolute; right: 12px; bottom: 12px; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: rgba(20, 22, 32, 0.5); color: #fff; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16); }
  .dim { filter: grayscale(1); opacity: 0.6; }
</style>

// The student forum's topics: their order, icon and tint (server logic/threads.py TOPICS). Labels and hints are i18n keys
// bd.topic.<topic> and bd.hint.<topic>. Line icons, as the rest of the app's controls (3D emoji are for content).
import type { Component } from 'svelte';
import Package from '@lucide/svelte/icons/package';
import Footprints from '@lucide/svelte/icons/footprints';
import LifeBuoy from '@lucide/svelte/icons/life-buoy';
import UsersRound from '@lucide/svelte/icons/users-round';
import MessagesSquare from '@lucide/svelte/icons/messages-square';
import type { Topic } from './api';

export const TOPICS: Topic[] = ['thing', 'go', 'help', 'vol', 'talk'];
export const TOPIC_ICON: Record<Topic, Component<{ size?: number; strokeWidth?: number }>> = {
  thing: Package, go: Footprints, help: LifeBuoy, vol: UsersRound, talk: MessagesSquare,
};
/** each topic's colour for its icon and label, readable as text in both themes (its tile: the same, faint) */
export const TOPIC_TINT: Record<Topic, string> = {
  thing: 'var(--warning-text)', go: 'var(--success-text)', help: 'var(--accent-text)',
  vol: 'color-mix(in srgb, var(--accent-2) 70%, var(--text))', talk: 'var(--text-2)',
};
/** "I'm in" counts people on these */
export const gathers = (t: Topic): boolean => t === 'go' || t === 'vol';

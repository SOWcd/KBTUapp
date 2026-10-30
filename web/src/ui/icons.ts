// One icon per concept (the design system): the nav, the capsule and the screens read the same mark from here, so a
// thing never has two. Add a concept when a second place needs it, not before (each import lands in the main chunk).
import type { Component } from 'svelte';
import Ticket from '@lucide/svelte/icons/ticket';
import MessagesSquare from '@lucide/svelte/icons/messages-square';
import Shapes from '@lucide/svelte/icons/shapes';
import CircleUserRound from '@lucide/svelte/icons/circle-user-round';
import type { Tab } from '../lib/state/ui.svelte';

/** the tabs, in the bar and in the capsule's inline title (Clubs: not `landmark`, which reads "government") */
export const TAB_ICON: Record<Tab, Component<any>> = { afisha: Ticket, forum: MessagesSquare, club: Shapes, profile: CircleUserRound };

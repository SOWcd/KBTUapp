import type { Component } from 'svelte';
import { open } from '../lib/state/ui.svelte';
import Menu from './Menu.svelte';

export type MenuItem = {
  label: string;
  /** a lucide icon at the item's end */
  icon?: Component<any>;
  /** a pick: true on the current choice (it gets the check), false on the others; leave it out for an action */
  checked?: boolean;
  /** red, and last after a line, whatever the order given; confirm it with the app's Ask in onselect */
  destructive?: boolean;
  disabled?: boolean;
  /** the menu goes at once, with no exit, before onselect runs: a pick that starts a view transition (theme, language)
   *  would be caught in its snapshot */
  instant?: boolean;
  onselect: () => void;
};

/** An iOS pull-down at `anchor` (a row's value, a ⋯ button), for 2-6 choices and for every ⋯. It is an overlay in the
 *  stack, so a tap outside, Escape and Telegram's Back close it, never the page under it. `align`: which edge of the
 *  menu lines up with the anchor's (by default the side of the screen the anchor is on). Returns the overlay's id. */
export function menu(anchor: Element, items: MenuItem[], align?: 'start' | 'end'): number {
  return open(Menu, { anchor, items, align });
}

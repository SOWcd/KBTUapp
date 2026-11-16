// DMP at a desk: the registry laid out wide on a computer's screen, and opened by itself there at launch.

/** From this width the registry is a table with the roster beside it (phones never reach it). */
export const WIDE = '(min-width: 1000px)';

/** The launch opens the registry by itself: an overseer on a computer, on a plain launch (a link of its own wins). */
export const deskRegistry = (oversee: boolean | undefined, startParam: string, computer: boolean): boolean =>
  computer && !!oversee && !startParam;

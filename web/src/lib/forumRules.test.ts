// The app's as-you-type rules agree with the server's on every shared case (server/tests/fchannel_rules.json).
import { expect, it } from 'vitest';
import { broken, meaningful } from './forumRules';
import rules from '../../../server/tests/fchannel_rules.json';

it.each(rules.cases as [string, string | null][])('%j is %s', (text, kind) => {
  expect(broken(text)).toBe(kind);
});

it.each(rules.meaningful as [string, boolean][])('%j is meaningful: %s', (text, ok) => {
  expect(meaningful(text)).toBe(ok);
});

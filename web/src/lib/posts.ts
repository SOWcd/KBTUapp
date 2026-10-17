// Post labels (SPEC §4.10): the composer's chips by code, named in the UI language; an older free-text tag shows as is.
import type { PostTag } from './api';
import { t } from './i18n/index.svelte';

export const POST_TAGS: PostTag[] = ['important', 'recruiting', 'results', 'news'];
export const tagName = (tag: string | null): string | null =>
  tag && (POST_TAGS as string[]).includes(tag) ? t(`tag.${tag}` as 'tag.news') : tag;

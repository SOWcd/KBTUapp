// The version of the privacy policy and terms a student agrees to (kbtu.sow.kz/privacy and /terms). A new one asks every
// student once more (ConsentGate). v2: the full policy and the terms; v3: what a deleted account keeps
// without the name (H2). With the forum on the server asks for 2026-11-v10 (/api/me consentNow): its part of the policy.
export const CONSENT_VERSION = '2026-11-v9'; // v9-v12 (Nov 2): the nick rule, a nick no longer hides the name (section 4)
// the server's other versions (logic/account.py): the forums' sections in force
export const CONSENT_BOARD = '2026-11-v11', CONSENT_BOTH = '2026-11-v12'; // v7, v8 until Nov 2 (v5, v6 until Oct 31)
// with the channel's comments on (FORUM_GROUP) the server adds this to whichever version is in force
export const CONSENT_TGC = '+tgc1';
// with the forum channel on (FORUM_CHANNEL) the server adds this after that: the section on posts in the channel
export const CONSENT_FCH = '+fch1';
// with any of those on the server adds this last: students' texts to more AI providers (the policy's section 5)
export const CONSENT_AI = '+ai1';

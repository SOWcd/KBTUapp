// The version of the privacy policy and terms a student agrees to (kbtu.sow.kz/privacy and /terms). A new one asks every
// student once more (ConsentGate). v2: the full policy and the terms; v3: what a deleted account keeps
// without the name (H2). With the forum on the server asks for 2026-11-v14 (/api/me consentNow): its part of the policy.
export const CONSENT_VERSION = '2026-11-v13'; // v13-v16 (Nov 2): a deleted account's posts and comments stay, nameless (section 7); v9-v12: the nick rule
// the server's other versions (logic/account.py): the forums' sections in force
export const CONSENT_BOARD = '2026-11-v15', CONSENT_BOTH = '2026-11-v16'; // v11, v12 until the deleted-account change (v7, v8; v5, v6 before)
// with the channel's comments on (FORUM_GROUP) the server adds this to whichever version is in force
export const CONSENT_TGC = '+tgc1';
// with the forum channel on (FORUM_CHANNEL) the server adds this after that: the section on posts in the channel
export const CONSENT_FCH = '+fch4'; // fch3 until Nov 4 (the check's explanation, appeals, reply limits), fch2 until Nov 3 (the anonymous author's replies), fch1 until Nov 2 (the feed's commenters' faces and reactions)
// with any of those on the server adds this last: students' texts to more AI providers (the policy's section 5)
export const CONSENT_AI = '+ai1';

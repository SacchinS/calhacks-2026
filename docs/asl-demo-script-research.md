# ASL demo script: research notes

**Status: research draft. A Deaf signer has not checked any of this yet. Do not rehearse it as final.**

**Scope change (Oct 24): the project is Google Meet only.** Only Moment 3 (the Meet greeting), the control signs, and the fingerspelling notes still apply. Moments 1, 2 and 4 (Claude Code and Siri) are kept as research; their code is on the `archive/claude-code-siri` branch. The live demo adds fingerspelled names and jargon (`fs-PRIYANKA`, `fs-KUBERNETES`), which the grammar notes below cover: names and technical terms are typically fingerspelled.

We're a hearing team, and nobody on it knows ASL. This file collects what published ASL references say about each sign and sentence pattern in the demo, so we aren't guessing. Every sign claim links to a page we actually opened (fetched Oct 23, 2026). Anything without a source is marked **UNVERIFIED**.

**Important limit.** The sources document individual signs and general grammar patterns. None of them contains our exact demo sentences. Each full sentence below is assembled from sourced signs, using a sourced pattern that's named in its row. Assembled is not the same as attested. Have a Deaf signer approve or rewrite every sentence, and get the signs from that person's video, not from these text descriptions. (Prof. Lance Forshay is the obvious person to ask; see `docs/user-research.md`.)

Sources used:
- **Lifeprint (ASLU)**: Dr. Bill Vicars, Deaf ASL instructor. Sign pages are at `https://www.lifeprint.com/asl101/pages-signs/<letter>/<word>.htm`.
- **Handspeak**: Jolanta Lapiak, Deaf ASL dictionary author.
- **StrongASL**: Paul Kelly, certified interpreter and CODA. Used only for REMIND, because the Lifeprint REMIND page is an empty stub.

Gloss conventions: CAPS = sign; `fs-` = fingerspelled; `#` = lexicalized fingerspelling; `me-VERB-you` = a directional verb moving from signer to addressee; `/\` = raised eyebrows over the preceding part (Handspeak notation); `IX` = point.

"Kaggle" = the 250-sign Kaggle ISLR vocabulary listed in `docs/asl-vocab-check.md`. "No" means we'd need to custom-train it.

---

## Moment 1: Claude Code kick-off (build request + YES)

### Candidate sentences (pick one)

All three use the Handspeak imperative pattern: object first under raised brows, then the verb, with the subject "you" usually dropped ([Handspeak: making a command or request](https://www.handspeak.com/topic/195/)). Lifeprint says plain SVO is the basic order, and topicalization (topic first, brows raised) is common but shouldn't be overused ([Lifeprint SVO/topicalization](https://lifeprint.com/asl101/topics/subject-verb-object-asl-sentence-structure.htm)). The plain `MAKE WW ...` order is the fallback.

| # | Gloss | English Claude should produce | Why | New signs needed |
|---|---|---|---|---|
| **A (recommended)** | `FOOD STORE /\ WW MAKE` (alt: `MAKE WW, FOOD STORE`) | "Build a website for a grocery store." | FOOD + STORE = "grocery store" is on Lifeprint's STORE page. FOOD, STORE and MAKE are all in Kaggle, and STORE comes back in the Siri moment. Only WW needs training. | WW |
| B | `MY DOG /\ WW MAKE` | "Build a website about my dog." | Fun visual page. MY (minemy) and DOG are in Kaggle. But Lifeprint lists several "right" DOG variants, and the variant in the Kaggle data is UNVERIFIED. | WW |
| C | `WW MAKE, fs-<NAME>` | "Build a personal website for <name>." | Lifeprint's fingerspelling page says names are typically fingerspelled. Depends on the fingerspelling model working live. | WW |

Then **YES** confirms the plan Claude shows.

**Signs to avoid here:**
- **ABOUT**: Lifeprint says the general ABOUT sign often isn't the natural choice ([about](https://www.lifeprint.com/asl101/pages-signs/a/about.htm)), so the candidates use topicalization instead.
- **PIZZA**: very regional; Lifeprint says "check with your local Deaf" ([pizza](https://www.lifeprint.com/asl101/pages-signs/p/pizza.htm)).
- **COFFEE**: Lifeprint warns MAKE and COFFEE look alike ([make](https://www.lifeprint.com/asl101/pages-signs/m/make.htm)).

### Sign table

| Sign | Gloss | Source | Kaggle? | Hands | Notes |
|---|---|---|---|---|---|
| WEBSITE | `WW` | [Lifeprint website](https://www.lifeprint.com/asl101/pages-signs/w/website.htm), [web](https://www.lifeprint.com/asl101/pages-signs/w/web.htm) | No | 1 | A W done twice with a small arc. Lifeprint's example: `MY FAVORITE WW? LP!`. Can look like "66"; mouthing disambiguates. Don't fingerspell W-E-B-S-I-T-E. |
| MAKE | `MAKE` | [Lifeprint make](https://www.lifeprint.com/asl101/pages-signs/m/make.htm), [create](https://www.lifeprint.com/asl101/pages-signs/c/create.htm) | Yes | 2 | Stacked fists twist. Lifeprint says CREATE as a verb is signed MAKE, and BUILD ([build](https://www.lifeprint.com/asl101/pages-signs/b/build.htm)) means building construction-style. Looks like COFFEE. |
| FOOD | `FOOD` | [Lifeprint store](https://www.lifeprint.com/asl101/pages-signs/s/store.htm) (FOOD + STORE = grocery store), [food](https://www.lifeprint.com/asl101/pages-signs/f/food.htm) | Yes | 1 | |
| STORE | `STORE` | [Lifeprint store](https://www.lifeprint.com/asl101/pages-signs/s/store.htm) | Yes | 2 | Flattened-O hands pivot forward twice. A single movement = SELL, though some signers reverse this. |
| MY | `MY` | [Lifeprint my](https://www.lifeprint.com/asl101/pages-signs/m/my.htm) | Yes (`minemy`) | 1 | Flat hand on chest. |
| DOG | `DOG` | [Lifeprint dog](https://www.lifeprint.com/asl101/pages-signs/d/dog.htm) | Yes | 1 | Several variants (finger snap, leg slap plus snap, etc.). Lifeprint recommends the "DG" snap. |
| Name | `fs-...` | [Lifeprint fingerspelling](https://www.lifeprint.com/asl101/fingerspelling/fingerspelling.htm) | Fingerspelling model | 1 | Names, titles and brands are typically spelled. |
| YES | `YES` | [Lifeprint yes](https://www.lifeprint.com/asl101/pages-signs/y/yes.htm) | Yes | 1 | S hand "nods" at the wrist. |

Related tech signs we checked (not used in the script):
- **INTERNET** ([Lifeprint](https://www.lifeprint.com/asl101/pages-signs/i/internet.htm)): two-handed; middle fingers brush.
- **COMPUTER** ([Lifeprint](https://www.lifeprint.com/asl101/pages-signs/c/computer.htm)): many regional variants; Lifeprint says "check with your local Deaf". Avoid it.
- **PROGRAM** ([Lifeprint](https://www.lifeprint.com/asl101/pages-signs/p/program.htm)).
- **CODE** ([Lifeprint](https://www.lifeprint.com/asl101/pages-signs/c/code.htm)): Lifeprint calls its sign a "protologism", so fingerspell C-O-D-E or use PROGRAM.
- **PAGE** ([Lifeprint](https://www.lifeprint.com/asl101/pages-signs/p/page.htm)): book page.
- Lifeprint's `site.htm` and `text.htm` pages are empty stubs, so we have no evidence for them.

---

## Moment 2: Siri reminder ("Remind me tomorrow morning to buy milk")

**Recommended gloss:** `TOMORROW MORNING, you-REMIND-me BUY MILK`
(optional longer version: `TOMORROW MORNING, you-REMIND-me FOOD STORE BUY MILK`)

How it's built:
- **Time first.** Lifeprint describes TIME–TOPIC–COMMENT as a common order ([Lifeprint ch. 4](https://www.lifeprint.com/asl101/book/chapter4.htm)), but also calls "time first" partly a myth that learners overapply ([time-first](https://www.lifeprint.com/asl101/topics/time-first.htm)). Lifeprint's own practice sentences open with the time sign ("TOMORROW AFTERNOON, YOU what-DO?", "TOMORROW BREAKFAST YOU WANT ...?", "TOMORROW you-HELP-me, DON'T-MIND?" on the [TOMORROW page](https://www.lifeprint.com/asl101/pages-signs/t/tomorrow.htm)). Our sentence copies that shape.
- **REMIND is a real sign; don't fingerspell it.** This replaces the earlier `#REMIND` gloss. Handspeak says REMIND "can be inflected depending on the verb agreement" ([Handspeak 4263](https://www.handspeak.com/word/4263/)), so "remind me" moves toward the signer. The exact inflected form is **UNVERIFIED in text**; get it from a Deaf signer.
- **TOMORROW MORNING** as a compound time phrase is **UNVERIFIED**. The sources only show the parallel "TOMORROW AFTERNOON".

| Sign | Gloss | Source | Kaggle? | Hands | Notes |
|---|---|---|---|---|---|
| TOMORROW | `TOMORROW` | [Lifeprint tomorrow](https://www.lifeprint.com/asl101/pages-signs/t/tomorrow.htm) | Yes | 1 | A double movement turns it into a different meaning (DAILY/every day), so do a single movement. |
| MORNING | `MORNING` | [Lifeprint morning](https://www.lifeprint.com/asl101/pages-signs/m/morning.htm) | Yes | 2 | The non-dominant arm is the horizon and the flat hand rises. GOOD-MORNING is often one-handed. |
| REMIND | `you-REMIND-me` | [Handspeak](https://www.handspeak.com/word/4263/), [StrongASL](https://www.strongasl.com/american-sign-language-dictionary/words/remind) | **No** | 2 (per StrongASL) | StrongASL: bent dominant fingertips tap the non-dominant vertical index finger. The [Lifeprint page](https://www.lifeprint.com/asl101/pages-signs/r/remind.htm) is an empty stub. |
| BUY | `BUY` | [Lifeprint buy](https://www.lifeprint.com/asl101/pages-signs/b/buy.htm) | **No** | 2 | Like taking money from your palm and moving it forward. |
| MILK | `MILK` | [Lifeprint milk](https://www.lifeprint.com/asl101/pages-signs/m/milk.htm) | Yes | 1 | C hand squeezes to S, repeated. |
| FOOD STORE | `FOOD STORE` | [Lifeprint store](https://www.lifeprint.com/asl101/pages-signs/s/store.htm) | Yes / Yes | 1 / 2 | Optional. |

The weather fallback `TOMORROW RAIN` *is* attested as a Lifeprint practice sentence: "TOMORROW RAIN? GAME CANCEL." (a rhetorical question) and "YOU THINK TOMORROW RAIN?" ([TOMORROW page](https://www.lifeprint.com/asl101/pages-signs/t/tomorrow.htm)). We didn't look up the RAIN sign itself, and as a question it needs raised brows.

---

## Moment 3: Meet greeting

**Recommended exchange (signer's side):**
1. `HELLO, NICE MEET-you` → "Hello, nice to meet you."
2. `HOW YOU?` (raised brows / friendly face) → "How are you?"
3. In reply: `FINE` or `FINE, THANK-YOU` → "I'm fine, thanks."
4. Closing: `THANK-YOU`. (`BYE` is in Kaggle but wasn't researched.)

Lifeprint attests each phrase: "NICE MEET-you" (It is nice to meet you) on the [NICE page](https://www.lifeprint.com/asl101/pages-signs/n/nice.htm); "Hello, how are you?" as a wave plus HOW YOU on the [HOW page](https://www.lifeprint.com/asl101/pages-signs/h/how.htm); FINE as the answer on the [FINE page](https://www.lifeprint.com/asl101/pages-signs/f/fine.htm).

If someone asks the signer's name, Lifeprint says the natural answer is just the fingerspelled name, not "MY NAME ..." ([NAME page](https://www.lifeprint.com/asl101/pages-signs/n/name.htm)). That only works if the fingerspelling model is live. Since the app already speaks the intro, we recommend skipping a signed name.

| Sign | Gloss | Source | Kaggle? | Hands | Notes |
|---|---|---|---|---|---|
| HELLO | `HELLO` | [Lifeprint hello](https://www.lifeprint.com/asl101/pages-signs/h/hello.htm) | Yes | 1 | A natural wave with a side-to-side movement (waving goodbye uses a bending motion instead). |
| NICE | `NICE` | [Lifeprint nice](https://www.lifeprint.com/asl101/pages-signs/n/nice.htm) | **No**, but `clean` is | 2 | Lifeprint: NICE and CLEAN are the same sign. We could reuse the Kaggle `clean` class and map it to "nice" when it comes before MEET. Kaggle's form of CLEAN is **UNVERIFIED**; test it. |
| MEET | `MEET-you` | [Lifeprint meet](https://www.lifeprint.com/asl101/pages-signs/m/meet.htm) | **No** | 2 | Two index fingers come together. Directional. With D hands it means DATE instead. |
| HOW | `HOW` | [Lifeprint how](https://www.lifeprint.com/asl101/pages-signs/h/how.htm) | **No** | 2 | Curved hands roll forward. |
| YOU | `YOU` | [Lifeprint you](https://www.lifeprint.com/asl101/pages-signs/y/you.htm) | **No** | 1 | Point at the addressee. Our own (unsourced) engineering concern: a recognizer may confuse it with other points (THERE, HE/SHE). |
| FINE | `FINE` | [Lifeprint fine](https://www.lifeprint.com/asl101/pages-signs/f/fine.htm) | Yes | 1 | Thumb of a 5 hand touches the chest. |
| THANK-YOU | `THANK-YOU` | [Lifeprint thank you](https://www.lifeprint.com/asl101/pages-signs/t/thankyou.htm) | Yes (`thankyou`) | 1 | Flat hand moves from the lips forward and down, with a smile. Looks like one-handed GOOD ([good](https://www.lifeprint.com/asl101/pages-signs/g/good.htm)). |
| NAME | `NAME` | [Lifeprint name](https://www.lifeprint.com/asl101/pages-signs/n/name.htm) | No | 2 | Not recommended; see above. |

---

## Moment 4: Re-prompt (edit the page)

**Recommended:** `TITLE /\ RED` (alt: `TITLE /\ CHANGE RED`) → "Make the title red."
**Alternative:** `TITLE /\ BIG-ER` or `TITLE /\ MORE BIG` → "Make the title bigger."

How it's built:
- Object first under raised brows, then the comment, following Handspeak's imperative pattern ([Handspeak 195](https://www.handspeak.com/topic/195/)).
- Whether ASL says "make X red" with a bare color, with CHANGE, or another way is **UNVERIFIED**.
- We recommend the red version over bigger because RED is in Kaggle and is one sign, and because the sources disagree on "bigger":
  - Lifeprint says BIG plus an "-ER" suffix sign, and a bigger movement means more emphasis ([comparatives](https://lifeprint.com/asl101/pages-layout/comparatives.htm)).
  - Handspeak says ASL can't easily add -ER, and gives `MY CAR /\ YOUR CAR MORE BIG` ([Handspeak comparatives](https://www.handspeak.com/topic/486/)). Handspeak's BIG entry also says to inflect BIG for "bigger and bigger" ([Handspeak big](https://www.handspeak.com/word/195/)).
- The earlier gloss `MAKE TITLE RED` is English word order. No source supports MAKE as a causative there, so it's **UNVERIFIED**.

| Sign | Gloss | Source | Kaggle? | Hands | Notes |
|---|---|---|---|---|---|
| TITLE | `TITLE` | [Lifeprint quote/topic/subject/title](https://www.lifeprint.com/asl101/pages-signs/q/quote.htm), [Handspeak title](https://www.handspeak.com/word/2235/) | **No** | Not stated in the text we read (**UNVERIFIED**) | Lifeprint: the QUOTE sign also means title, topic and subject. Handspeak has a TITLE sign plus a variation (video only). Lifeprint's own `title.htm` page is an empty stub. |
| RED | `RED` | [Lifeprint red](https://www.lifeprint.com/asl101/pages-signs/r/red.htm) | Yes | 1 | Index finger strokes down from the lips. PINK is the same movement with a P/K hand ([pink](https://www.lifeprint.com/asl101/pages-signs/p/pink.htm)), so they're look-alikes. An R-initialized version is not recommended. Other colors (blue, green, yellow, …) are in Kaggle too. |
| CHANGE | `CHANGE` | [Lifeprint change](https://www.lifeprint.com/asl101/pages-signs/c/change.htm) | **No** | 2 | Optional. |
| COLOR | `COLOR` | [Lifeprint color](https://www.lifeprint.com/asl101/pages-signs/c/color.htm) | **No** | 1 | Fingers flutter in front of the chin. Not needed if you name the color. |
| BIG | `BIG` | [Lifeprint big](https://www.lifeprint.com/asl101/pages-signs/b/big.htm), [Handspeak big](https://www.handspeak.com/word/195/) | **No** | 2 | Hands move apart (flat or bent-L). The size of the movement shows the size of the thing. Initialized L/B forms are Signed English, not ASL. |
| MORE | `MORE` | [Lifeprint more](https://www.lifeprint.com/asl101/pages-signs/m/more.htm) | **No** | 2 | Flattened-O hands are brought together. |

---

## Control signs

| Sign | Source | Kaggle? | Hands | Conflict |
|---|---|---|---|---|
| YES | [Lifeprint yes](https://www.lifeprint.com/asl101/pages-signs/y/yes.htm) | Yes | 1 | It's a real word inside sentences too, e.g. answers. |
| NO | [Lifeprint no](https://www.lifeprint.com/asl101/pages-signs/n/no.htm) | Yes | 1 | Lifeprint describes NO as lexicalized N-O ([lexicalized fingerspelling](https://www.lifeprint.com/asl101/fingerspelling/fingerspellinglexicalized.htm)), and it's usually paired with a head shake. |
| FINISH | [Lifeprint finish](https://www.lifeprint.com/asl101/pages-signs/f/finish.htm) | Yes | 2 | **Meaning clash.** FINISH means done, already, or completed (it marks past or completed action inside sentences), and a sharp version means "cut it out". If FINISH also means SEND, a signer saying "I already bought milk" (FINISH BUY) would trigger a send. Options: require a hold or pause before and after, or have a Deaf advisor pick a different end signal. |

---

## Custom signs to train (not in the Kaggle 250)

**Needed for the recommended script:**
- WW (website)
- REMIND (the inflected you-REMIND-me form)
- BUY
- MEET (the MEET-you form)
- NICE (or reuse Kaggle `clean`)
- HOW
- YOU
- TITLE

**Only if using the alternatives:**
- CHANGE, BIG, MORE (the "bigger" re-prompt)
- COLOR
- NAME

**Already in Kaggle:**
- MAKE, FOOD, STORE, MY (`minemy`), DOG
- TOMORROW, MORNING, MILK
- HELLO, FINE, THANK-YOU
- RED
- YES, NO, FINISH

Whether the Kaggle data uses the same variants as Lifeprint is **UNVERIFIED**; test each one live.

---

## Grammar notes (sourced)

- **Word order.** Basic transitive order is SVO. Topicalization moves the topic to the front under raised brows and a head tilt, and shouldn't be overused ([Lifeprint SVO](https://lifeprint.com/asl101/topics/subject-verb-object-asl-sentence-structure.htm)). Lifeprint also describes TOPIC–COMMENT and TIME–TOPIC–COMMENT, and notes that experts differ ([ch. 4](https://www.lifeprint.com/asl101/book/chapter4.htm)).
- **Time first** is common but overapplied; Lifeprint calls the strict rule partly a myth ([time-first](https://www.lifeprint.com/asl101/topics/time-first.htm)).
- **Commands and requests.**
  - PLEASE and MIND-NOT are common in requests. A general pattern is OSV: the object comes first under raised brows, then the brows return to neutral.
  - The subject "you" is often omitted.
  - There are formal and informal registers. Example: `/\KEY/\ GIVE-me PLEASE` ([Handspeak 195](https://www.handspeak.com/topic/195/)).
  - PLEASE tends to come at the end ([Lifeprint please](https://www.lifeprint.com/asl101/pages-signs/p/please.htm)).
- **Questions.**
  - Yes/no questions: raised brows, head tilted forward.
  - Wh-questions (who, what, where, when, why, how): furrowed brows, and the head may tilt. The wh-sign often goes at the end.
  - On short questions the brows can be held throughout; on longer ones they mark the relevant part ([Lifeprint NMM](https://www.lifeprint.com/asl101/pages-layout/nonmanualmarkers.htm), [grammar 17](https://www.lifeprint.com/asl101/topics/grammar17.htm), [facial expressions](https://www.lifeprint.com/asl101/topics/facial-expressions-in-sign-language.htm)).
- **Other non-manual markers.**
  - Raised brows also mark conditional ("if") clauses.
  - A head nod means affirmation; a head shake means negation.
  - Cheek-to-shoulder means "very near" or "very recent" ([Lifeprint NMM](https://www.lifeprint.com/asl101/pages-layout/nonmanualmarkers.htm)).
  - The "CHA" mouth shape on BIG means very big ([Lifeprint big](https://www.lifeprint.com/asl101/pages-signs/b/big.htm)).
- **What this means for our recognizer.** In ASL, the difference between a question and a statement, a topic, or a negation often sits on the face and head, not the hands.
  - A hands-only gloss stream loses that. `HOW YOU` vs `YOU FINE` (statement or question) can't be told apart from the hands alone.
  - MediaPipe Holistic already gives face landmarks. A brow-raise or furrow feature, or a head-shake feature, would let us send `?` and negation markers to Claude.
  - Until then, demo sentences should be ones whose meaning doesn't depend on the face (HOW is a wh-sign, so `HOW YOU` reads as a question anyway).
- **Fingerspelling.**
  - Names, places, titles of works, organizations and brands are typically fingerspelled, but skilled signers use signs and depiction whenever possible ([Lifeprint fingerspelling](https://www.lifeprint.com/asl101/fingerspelling/fingerspelling.htm)).
  - Lexicalized fingerspelling (`#`) is fingerspelling that has turned into a sign: letters dropped, movement added (e.g. #BUSY, #WHAT, #NO) ([Lifeprint](https://www.lifeprint.com/asl101/fingerspelling/fingerspellinglexicalized.htm)). Lifeprint's list includes #OK, #JOB, #DO, #IF, #ALL, #CAR, #BUS, #BANK, #BACK, #PIZZA ([list](https://www.lifeprint.com/asl101/topics/katie/lexicalizedfingerspelledwords.htm)).
  - These are signs, so a letter-by-letter fingerspelling model will likely miss them; train them as whole signs.
  - **#REMIND is not a thing in our sources.** REMIND has a sign.
- **Directional verbs.** MEET, HELP, REMIND (and others) change their path depending on who acts on whom: me-MEET-you, you-HELP-me ([Lifeprint meet](https://www.lifeprint.com/asl101/pages-signs/m/meet.htm), [help](https://www.lifeprint.com/asl101/pages-signs/h/help.htm), [Handspeak REMIND](https://www.handspeak.com/word/4263/)). Train the exact form used in the script, and expect other directions to be misread.

---

## Caveats

1. **Sentences are assembled, not attested.** Only the Meet phrases (NICE MEET-you, HELLO HOW YOU, FINE) appear in a source as whole phrases.
2. **Regional variation.** Lifeprint explicitly flags COMPUTER, PIZZA and DOG as varying. Rule: one signer, one consistent variant for both training and demo, and no claims of generality.
3. **Look-alike signs** (risk of misrecognition):
   - THANK-YOU / GOOD
   - MAKE / COFFEE
   - MEET / DATE
   - RED / PINK
   - WW / 66
   - STORE / SELL (single vs double movement)
   - TOMORROW / every-day (double movement)
   - NAME (noun, double tap) / NAME (verb, single tap)
   - NICE = CLEAN (identical)
   - YOU vs any other point
4. **Face-dependent grammar** is invisible to a hands-only model (see grammar notes).
5. **FINISH as SEND** clashes with FINISH's real meaning.
6. **Text descriptions aren't enough to learn a sign.** Movement, palm orientation and location are easy to get wrong from words alone. Learn every sign from a Deaf signer or from the source videos.
7. **Respect.** UW Deaf faculty asked hearing developers to include Deaf people on the team (`docs/user-research.md`). Show signing a Deaf person has approved, and credit them.

---

## Open questions (a Deaf signer must answer these before the demo)

1. Are the four recommended sentences natural ASL? If not, how would you sign them?
2. What's the correct inflected form of you-REMIND-me? Is `TOMORROW MORNING` the natural time phrase?
3. For "make the title red": bare `TITLE RED`, `TITLE CHANGE RED`, or something else? For "bigger": BIG-ER, MORE BIG, or an inflected BIG?
4. Which TITLE sign do you use (Lifeprint's QUOTE/TITLE sign or a Handspeak variant)? Is it one- or two-handed?
5. Is WW the WEBSITE sign you use? Is there a better sign for "build/make a website"?
6. Is FINISH acceptable as an end/send signal, or would something else feel more natural?
7. Which variants do you use for DOG, COMPUTER and HELP, if the script ends up using them?
8. Would you sign a name in a Meet greeting, or leave it to the spoken intro?
9. **UNVERIFIED (no source found):**
   - the full-sentence orders in all four moments
   - TOMORROW MORNING as a compound
   - the color-change construction
   - the handedness of TITLE
   - which variants the Kaggle ISLR data uses

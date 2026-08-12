<a name="readme-top"></a>

# Verse &amp; Quote of the Day

https://bell-kevin.github.io/verse/

A plain website that shows, every day:

- a **Book of Mormon verse of the day**,
- a **Come, Follow Me verse of the day** drawn from the current week's reading, and
- a **General Conference quote of the day**.

No app, no account, no sign-in. Open the page and read it.

**Contents** — [Why this exists](#why-this-exists) · [What is in here](#what-is-in-here) ·
[How the readings are chosen](#how-the-readings-are-chosen) ·
[How it keeps itself current](#how-it-keeps-itself-current) ·
[Light and dark](#light-and-dark) · [Where a link lands](#where-a-link-lands) ·
[Sharing a card](#sharing-a-card) ·
[It works with JavaScript switched off](#it-works-with-javascript-switched-off) ·
[Running it yourself](#running-it-yourself) ·
[Licensing](#licensing-and-what-the-licence-does-not-cover)

## Why this exists

The Church publishes a Verse of the Day and a Quote of the Day, but they are
only reachable through the Gospel Library and Book of Mormon mobile apps, or on
`churchofjesuschrist.org` after signing in. There is no public feed: the
`my-home` page serves a "Sign in to access personalized content" prompt to
anonymous visitors, and its data route redirects to the login flow.

This project does **not** work around that. It does not log in, store
credentials, or republish anything that sits behind the sign-in wall. Instead it
builds its own daily readings from the parts of `churchofjesuschrist.org` that
anyone can already read without an account, and serves them as a static page.

The picks are therefore *not* the Church's official daily selections. The
Come, Follow Me verse does follow the same weekly curriculum the Gospel Library
verse is drawn from, so it stays in step with what wards are studying.

The page's footer links on to the Church's own Newsroom releases, for the same
reason the readings are built the way they are: that page is public, it needs no
account, and a reader who came for the day's verse and wants the week's news
should not have to sign in to get it either.

## What is in here

| Path | What it is |
| --- | --- |
| `index.html` | The site. **Generated** — edit `tools/template.html`, not this. |
| `tools/build_daily.py` | The builder: fetches, chooses, writes the calendar, renders the page. |
| `tools/test_readings.py` | Checks the rules that decide a reading against verses ruled on by hand. |
| `tools/readings_cases.json` | Those verses, as published. **Generated** — see `--refresh`. |
| `tools/test_links.py` | Checks that a link opens its verse where a reader can see it. |
| `tools/template.html` | The page itself, with placeholders where the day's readings go. |
| `data/daily.json` | The prebuilt calendar — two years of daily picks, about 1 MB. |
| `assets/app.js` | The enhancement script: theme, share, and correcting the day. |
| `assets/style.css` | The styling. |
| `assets/speakers/` | Speaker photos, downloaded at build time and committed. |
| `.github/workflows/deploy.yml` | The scheduled builds and the Pages deployment. |
| `.cache/` | Memoised API responses. Not served, not committed; safe to delete. |

The whole builder is one standard-library Python file, so CI installs nothing.

## How the readings are chosen

`tools/build_daily.py` reads three public sources through the study API, decides
what each day of the next two years should show, and writes the result to
`data/daily.json`. The page is then rendered from that calendar with the current
day's readings already in the markup.

The problem each card solves is the same one: **most verses and most paragraphs
do not stand on their own.** A verse of a genealogy, or a paragraph that begins
"But she had not told him yet", is fine where it sits and useless as the one
thing someone reads today. So each source is filtered down to what reads well
cold, and then ranked, and the ranking is what the calendar is dealt from.

### The Book of Mormon verse

All 239 chapters are fetched — 6,604 verses — and each one is asked two
questions.

**Can it stand alone at all?** A verse is dropped if it is shorter than about a
sentence or longer than a comfortable card (90–340 characters), if it is
plainly bookkeeping — `begat`, `the record of`, `the plates of`, pitching tents,
journeying in the wilderness — or if it is not a whole thought to begin with:

- a verse opening on a relative pronoun — *That ye may not be cursed with a
  sore cursing…*, *Whom I shall see for myself…* — is the back half of a
  sentence that began in the verse before, and no amount of doctrine in the
  rest of it makes it a reading. The conjunction in front can be stacked, and
  one word of allowance for it missed *And also that we may preserve unto them
  the words which have been spoken by the mouth of all the holy prophets* — 1
  Nephi 3:20, whose sentence says what they are preserved *for* in 3:19. Two
  words are allowed now, guarded, because that second step reaches *that* used
  as a determiner: *And again, that same God has brought our fathers out of the
  land of Jerusalem* is a whole sentence with a subject in it;
- a verse that only introduces the speech in the next one — *Then Job answered
  and said,* — is the label, not the reading;
- a verse with **a "he" it never answers**. This is the one that decides most
  verses, and **number is what it turns on.**

  A plural reads as generic when the verse says what they *do*. *Nevertheless
  they did fast and pray oft, and did wax stronger and stronger in their
  humility, and firmer and firmer in the faith of Christ* never says who *they*
  were and loses nothing by it: a reader supplies "people who do this" and the
  verse means exactly what it meant. That holds exactly as far as there is a
  "this" to supply. **A verse that only reports what was done to them** offers
  nothing to stand in for the name — *They are raised to dwell with God who has
  redeemed them; thus they have eternal life through Christ* is Mosiah 15:23,
  and who is raised is the whole question. The answer is 15:24, *these are they
  that have died before Christ came, in their ignorance*, which this build
  already refuses for pointing at it. Alone, the verse promises the
  resurrection to somebody it declines to name. What is let through is the
  predicate that answers the pronoun itself: a verse saying what they were
  *called* has named them — *And they were called the people of God* — and so
  has *they were men of truth and soberness*.

  A singular cannot be read either way. *Behold, he
  offereth himself a sacrifice for sin, to answer the ends of the law* is
  doctrine as plain as any in the book, and still lands wrong on anyone who
  does not already know that *he* is Christ — which 2 Nephi 2:6 says and 2
  Nephi 2:7 does not.

  So a plural is asked only whether the verse ever has them act, and **a
  singular has to find its referent inside its own verse.** Position is the
  whole of the test. *And the Lord did pour
  out his Spirit upon them* names the Lord before it says *his*, while *And
  they rehearsed unto his father all that had happened unto them; and his
  father rejoiced, for he knew that it was the power of God* reaches *God* only
  after three pronouns have gone by unanswered. That verse is Alma the younger
  coming back from the angel, and every word of it is doing its work — but a
  reader meeting it alone is never told who *they* are, whose father, or what
  happened.

  A name is not the only thing a pronoun can rest on. **A gospel word counts**
  — *And charity suffereth long … seeketh not her own* names nobody and wants
  nobody, because the *her* is charity, which the verse opened with. So does
  **a generic somebody**: *And likewise also is it counted evil unto a man, if
  he shall pray and not with real intent of heart* needs no one named, since *a
  man* is already who *he* is. What stays refused is the verse with nothing
  whatsoever in front of the pronoun — *And he commanded them that they should
  observe the sabbath day*, *And behold, he preached the word unto your
  fathers*, *And he had hope to shake me from the faith* (which is Sherem, the
  anti-Christ, and reads like counsel until you know that).

  Three exemptions. The generic **he that** means whoever fits rather than
  anybody in particular, needs nothing named, and opens some of the plainest
  teaching there is — *He that hath ears to hear, let him hear*. A verse
  arriving at **a conviction of its own** is kept whatever dangles in front of
  it, because the half a reader carries away speaks for itself: *Though he slay
  me, yet will I trust in him* is built exactly this way, and so is *For I know
  that my redeemer liveth, and that he shall stand at the latter day upon the
  earth*.

  And a verse that **states its teaching of a generic subject** is kept however
  it opened, because whatever dangles ahead of that is a turn in the argument
  and not the subject. Moroni 7:43 and 7:44 sit next to each other and divide
  on exactly this. 7:43 is *he cannot have faith and hope, save he shall be
  meek, and lowly of heart* — the pronoun is the only subject there is, and the
  reader has to bring one. 7:44 opens on a dangling *his faith and hope is
  vain* and then says the whole thing again with a subject in it: *none is
  acceptable before God, save the meek and lowly in heart; and if a man be meek
  and lowly in heart … he must needs have charity.*

  The verb is what makes that a subject, and requiring it matters. 2 Nephi 2:7
  closes *and unto none else can the ends of the law be answered* — that *none*
  is who the verse is **for**, not who it is **about**, and *he offereth
  himself a sacrifice for sin* still wants Christ named before it can be read.
  7:44's *none is acceptable* heads its own clause.

- **a verse pointing out of itself some other way.** A dangling speech
  attribution leaves the speaker behind instead of the subject: Job 1:21
  reaches the card as *And said, Naked came I out of my mother's womb*, because
  the man saying it is back in verse 20. Only an attribution naming nobody
  counts — *thus said Jesus Christ, the Son of God, unto his disciples* says
  whose words follow.

  A demonstrative standing where the subject goes is refused when it hands off
  to another pronoun or to an act the verse never describes: *And these are
  those who have part in the first resurrection* goes, and so does *Now this
  was done because there were so many people*, while *And this is my doctrine*
  and *And this is life eternal* stay. Used as a determiner it is left alone,
  since the subject is still to come and usually turns out to be the speaker —
  *But this much I can tell you…*, *These things have I written unto you*. So
  is **this is not all**: it is a turn in the argument rather than a subject,
  the teaching lands immediately after it, and what *all* referred to is no
  part of what the reader carries off — *But this is not all; ye must pour out
  your souls in your closets, and your secret places, and in your wilderness*
  wants nothing from the verse before it.

  An **"it" at the head of a verse** is doing one of two opposite jobs, and
  which one decides whether the verse survives. It is a placeholder when the
  verse goes on to say what it stands for — *It is better **that** one man
  should perish than that a nation should dwindle and perish in unbelief*, *It
  is a fearful thing **to fall** into the hands of the living God*, *It is better
  **to trust** in the Lord than to put confidence in man*. Nothing outside the
  verse is wanted, because the *it* is not about anything until the clause
  after it arrives.

  It is a pointer when that clause never comes. *But it is mockery before God,
  denying the mercies of Christ, and the power of his Holy Spirit, and putting
  trust in dead works* is Moroni 8:23, and the *it* is the baptising of little
  children, back in 8:22; as a day's reading it calls something a mockery and
  never says what. Helaman 7:18 is the same word answering a question asked in
  7:17 — *It is because you have hardened your hearts*. So the verse is read as
  far as its first full stop and the placeholder has to be filled inside it.
  Two constructions fill it without a word to mark them and are named directly:
  *it shall come to pass*, which always carries what follows with it, and *it
  is written*, where the *it* is the quotation after the comma.

  The lead-in comes off before any of this is asked, since scripture is
  punctuated as one continuous telling and nearly every verse opens by tying
  itself to the last — *And it came to pass that…* is scaffolding, not subject.

**How well does it stand alone?** What survives is scored.

The vocabulary is the foundation: **+1.6 for each distinct gospel word**,
counted by *stem*, so "commandment" and "commandments" in one verse count once
— the score rewards a verse that is *about* something, not one that repeats a
word. Stems matter more than they sound. An earlier list of whole words matched
*commandment* and missed *commandments*, matched *repent* and missed
*repentance*, matched *redeem* and missed *redeemer*; and since this count was
most of what decided a verse, what the list missed it decided wrongly. "For I
know that my redeemer liveth" scored **zero** and was dropped, while Satan's
speech eighteen chapters earlier — "Hast not thou made an hedge about him" —
scored 3.5 on the strength of one *blessed*, and was chosen.

On top of the vocabulary:

- **+3 for a note of conviction** — *I know that*, *I will trust*, *I would
  that ye should*.
- **+1.5 for counsel addressed to the reader** — *come unto*, *blessed are*,
  *if ye will*, *press forward*.
- **+1.5 for the shape of a verse people quote from memory**: short, whole,
  and with nobody named in it.
- **+1 for landing in the comfortable range** of 120–300 characters.

And against it:

- **−2.5 for a narrative opener** — *Nevertheless…*, *And when…*, *And they
  began…*. A verse that begins by picking up the thread of the last one needs
  the last one.
- **−4 for the voice of an accuser** — a verse that opens by challenging
  somebody, or that tells the reader their faith has been in vain. This is how
  the words of Satan and of the mockers came to be quoted as counsel: they use
  the vocabulary of the gospel to argue against it, so vocabulary alone cannot
  tell them apart from it.
- **−4 for a boast reported as inner speech** — *thou hast said in thy heart:
  I will ascend into heaven*. Scripture quotes the proud in order to answer
  them in the next verse, which a reader meeting the boast alone never reaches.
- **−3 for a report of people refusing what they were taught** — *they do set
  at naught his counsels*, *they harden their hearts against it*. A verse like
  that is *about* somebody rather than *to* the reader.
- **−3 for a complaint to God about what he has done** — *he hath destroyed me
  on every side*, *he hath stripped me of my glory*. Job's, mostly, and true to
  the book he is in, but his answer is thirty chapters away.
- **−0.9 for each distinct word of destruction or distress**, capped, so one
  hard word costs a verse a little and cannot sink it on its own: *wickedness
  never was happiness* is one of the best verses there is.
- **−0.7 for each distinct proper noun**. Dense names mean genealogy or a
  battle account. Deity is not counted — *the Lord*, *God*, *Jesus Christ* are
  what a verse of the day is most often about, so counting them charged a verse
  for its own subject — and neither are words capitalised only because they
  open a sentence, which used to tax "Naked came I out of my mother's womb" as
  heavily as a page of genealogy. (That verse is Job 1:21, and it is now turned
  down a step earlier, at the gate above, for opening on *And said,* with its
  speaker left in the verse before. *Naked* is still not a name, and the
  correction still matters everywhere else the word count reaches.)
- **−2.5 for a verse that is nothing but a question**, which the verse after it
  answers and the reader is left holding.
- **−0.8 for a verse ending in a colon or a semicolon**, which usually means the
  sentence finishes in the next one. A light touch rather than a refusal,
  because the King James punctuates whole sentences that way as well.

A verse needs 3.0 to be quotable at all. **1,873 of the 6,604 clear that bar**,
and 1,849 are left once the mastery passages below are taken out of the ordinary
pool — more than four years of reading either way, and it takes in a lot that
merely scraped through, so the ordinary days draw on **the best 500** instead
(the last build's cutoff was 6.7). Five hundred is chosen deliberately: it is
more than a year, so a reader is never shown a repeat inside their first year,
and it still turns over enough that a second year is not a rerun of the first.

Those 500 are shuffled with a fixed seed and then **dealt out round-robin by
book**, so consecutive days come from different places rather than marching
through Alma for a fortnight.

**Every fourteenth day is a scripture mastery passage instead.** The Church's
seminary programme names a hundred passages students are asked to know,
twenty-five from each standard work; they are the settled answer to "which
verses matter most", arrived at by people whose job was to decide it, so the
list is carried in the builder as fact rather than guessed at by the scoring
above. Twenty-five of them are from the Book of Mormon, and one comes round
every fourteen days — twenty-six turns a year for twenty-five passages, so each
is seen once a year and the extra turn walks the cycle forward, keeping a
passage off the same date two years running.

A mastery passage is quoted **whole**: every verse of it, joined into one
reading under one reference. Moroni 7:45's list of what charity is only lands
with 7:47's "charity is the pure love of Christ" after it, so it is not split
across days. Those verses are also removed from the ordinary pool, so you are
never shown a fragment of a passage a few days after seeing the passage.

### The Come, Follow Me verse

The week's page is what decides this card, and each week gets **up to seven
readings — one per day, Monday through Sunday.**

A week's title carries both things needed: `January 4–10. "We Have Come to
Worship Him": Matthew 2; Luke 2`. The dates before the first period give the
week's span; everything after the last colon is **the assignment**, parsed down
to a list of chapters (including forms like `1 and 2 Thessalonians` or `1–3
John`, which name no chapters and mean all of each).

The week's seven readings are then filled in this order:

1. **Any scripture mastery passage inside the week's assigned chapters**, quoted
   whole. That passage is the one a reader is likeliest to be asked about, and a
   given week only comes round once every four years, so it goes in whether or
   not the lesson page happens to hyperlink those particular verses.
2. **The verses the lesson page actually links** — every scripture hyperlink in
   the week's body is read for the verse numbers in its `id=` parameter, which
   is how the page marks exactly what it is pointing at. Those are ranked by
   the same standing-alone score the Book of Mormon card uses, plus **a bonus
   of 6 for sitting inside the week's own assigned chapters**, since those are
   what is discussed on Sunday. Come, Follow Me also points at cross-references,
   and the best of those are worth a day.

The assignment is a **bonus rather than an absolute**, and the week of `Job
1–3; 12–14; 19; 21–24; 38–40; 42` is the week that settled it. Ranking every
assigned verse above every cross-reference spent three days of that week on Job
19:2, 19:9 and 19:10 — *how long will ye vex my soul*, *he hath stripped me of
my glory*, *he hath destroyed me on every side* — while Ether 12:27 and D&C
121:7, which the lesson cites precisely because they answer Job, waited
outside. A bonus keeps the assignment first in every ordinary week and lets a
strong cross-reference in when the reading itself is a week of lament.

Two more rules keep a week from collapsing onto one passage:

- **No more than two days from any one chapter.** Come, Follow Me often links a
  long consecutive run — the lesson on Job cites verses 1 through 27 of Job 19's
  twenty-nine — and without a cap the week reads as a single passage dealt out
  slowly rather than as a walk through the whole assignment.
- **A verse must score 2.5 to be worth a day at all.** Below that the week
  simply runs shorter and its readings come round again, which is better than
  filling the last days with whatever was left.

Verses already inside a mastery passage placed that week are dropped, so a day
is not spent on a fragment of what another day quotes whole. Verses outside
60–400 characters are dropped as too slight or too long for the card, and the
structural tests the Book of Mormon card applies are applied here too — this
card used to check only the length, and let through readings like *…which was
spoken of the Lord by the prophet, saying,*.

That shared gate is why the pronoun rule above reaches this card as well, and
this is the card it was worth most to. The week on Job used to spend its second
day on *And said, Naked came I out of my mother's womb* — the words are Job's,
but the verse does not say so, because *Then Job arose, and rent his mantle* is
back in verse 20.

Refusing it is also what turned up the weakness in an earlier version of the
rule. With 1:21 gone the day fell to Job 1:16, *While he was yet speaking,
there came also another* — a messenger's report of a disaster to a man that
verse never names either — which a test looking only at the subject's place
walked straight past. Asking instead whether the *he* is ever answered inside
the verse catches both, and wherever in the verse they hide.

The week now opens on Job 1:1, passes through *though he slay me, yet will I
trust in him*, reaches **Job 19:25 — "For I know that my redeemer liveth"**,
which under the old scoring was not merely passed over but scored zero, and
closes on Job 42:2 — *I know that thou canst do every thing* — which is where
the assignment itself ends.

Once the seven are picked they are **put back into the order the assignment
runs**, so the week walks through the reading in sequence and arrives at church
on Sunday having read it, rather than meeting it in a jumble. At the last build
**74 of the calendar's 76 full weeks got their seven.**

Both of the short ones were held there by the two-a-chapter cap rather than by
the floor, which is the cap doing what it is for. The week on Esther had eight
verses worth a day but they sat in five chapters, so it ran six; the week on
Matthew 1; Luke 1 had twenty-seven, and twenty-four of them were in Luke 1
alone, so it ran five. Six days walking a week's whole reading is a better week
than seven days walking one chapter of it.

If a week's title cannot be parsed the builder treats that as *no opinion*
rather than *nothing assigned*, and takes the week's citations at face value —
better a card chosen a little less well than an empty one.

### The General Conference quote

The most recent conference whose talks are published is used (see
[below](#following-general-conference-automatically) for how that is decided).

**Church business is dropped first.** Conference is more than preaching:
officers are sustained, the audit is read, a solemn assembly is called. "We
invite the Quorum of the Twelve Apostles please to stand" is not a quote of the
day, so those items are left out of the pool entirely — recognised by their
titles, by an author line reading "Presented by" instead of "By", and by roles
like *auditing* or *managing director*.

Each remaining talk is read down to its endnotes — those are bibliography lines,
not anything worth quoting — and each paragraph is asked the same two questions
the verses are.

**Can it stand alone at all?** A paragraph is dropped if it is outside 90–420
characters, if it does not end in a full stop (or a question or exclamation
mark, with or without a closing quotation mark after it), or if it is one of the
things that only makes sense next to the paragraph before it:

- an opener that continues a thought — *But…*, *So…*, *However…*, *That…*,
  *He…*, *They…*, *I was…*, *After…*. This card has refused paragraphs on this
  ground since it was written, which is why its quotes read cleanly while the
  two scripture cards were still printing *And they rehearsed unto his father*;
  the fix above brings those two up to this standard. The possessives and
  objects — *His…*, *Their…*, *Them…* — were added here at the same time, for
  the same reason the subjects are refused: *Their example has stayed with me*
  is as unreadable cold as *They stayed with me*. It cost this conference's
  pool nothing, finding no paragraph the rest of the test was not already
  turning down;
- an adverb opener — *Tragically,…* almost always continues a story;
- storytelling rather than counsel, spotted by a subject-and-past-tense-verb
  pair in the opening — *he told*, *we went*, *I felt*, *she saw*. The verbs are
  named one by one rather than matched as any past tense, because "-ed" alone
  throws out the counsel that is phrased in it: *I have learned*, *I promised*;
- a dangling half-quotation — an odd number of quotation marks, or a paragraph
  that opens inside one;
- an academic aside — anything carrying `(see …)` or `(compare …)`;
- a list picked up several paragraphs later — *Second, the question is
  asked…* — which says nothing on its own;
- a paragraph about the talk it sits in: what the speaker will cover, what will
  appear in *the published version of my message*, what is left of their time.
  It reads as housekeeping anywhere but in its place;
- the greeting a talk opens with — *I am humbled by the privilege to speak to
  you*, *I pray that the Spirit will be with you and with me*. This is the
  counterpart of the closing formula below, but unlike a closing there is
  rarely a teaching inside one to salvage, so it is simply refused;
- the furniture of a session rather than the preaching in it — *the choir*,
  *we have just heard*, *welcome to this*.

**How much teaching does it carry?** What survives is scored on the turns of
phrase a talk is actually remembered by:

- **+4 for a witness** — *I testify*, *I bear solemn witness*, *I know that*,
  *I declare*;
- **+3.5 for an invitation** — *I invite*, *I plead*, *I urge*, *my prayer*,
  *may we*, *consider*, *begin today*;
- **+2 for a promise** — *the Lord will*, *will bless*, *will strengthen*,
  *blessings of*;
- **+1.2 for each distinct doctrinal word**, counted by stem as with the
  verses, so *covenant* and *covenants* count once between them;
- **+2.5 for being short enough to carry away** in one reading (130–260
  characters), **−1.5 for running past 300**;
- **−1.5 for every statistic** — a number of two digits or more, or the word
  *percent* — and **−0.5 for each distinct proper noun**: a report or an
  anecdote, not counsel;
- **−2.5 for a paragraph that is nothing but questions**, which sets something
  up rather than saying it.

**Being the right shape is not enough on its own.** The bonus for landing in
that comfortable 130–260 characters was, by itself, more than the floor a
paragraph had to clear — so paragraphs that said nothing whatsoever qualified
on length and went into the calendar. An airline's baggage handling: *"Fragile
items such as musical instruments are often hand-delivered to passengers."* A
family dog: *"Years ago our family had a little black dog, a toy poodle named
Lady."* Both cleared the bar with no gospel word in them at all. So what a
paragraph *says* is now measured separately from how it is shaped, and it has
to carry some teaching — roughly two gospel words, or one invitation — before
its shape counts for anything.

**A talk's closing is not its best line.** Every talk ends in the name of Jesus
Christ, and those closings were the highest-scoring paragraphs of the whole
conference: dense with gospel words, almost always carrying an invitation or a
blessing. The scoring loved them and the quotas took them first, so **one in
six of every quote chosen was a benediction** — *"…is my prayer and my blessing
in the holy name of Jesus Christ, amen."*

Refusing all of them went too far, though. Some are nothing but the form of
words; others are a real teaching with the formula added after, and for a
speaker who writes in long paragraphs the closing may be the only thing short
enough to quote at all. Refusing every one of them cost Elder Walker's talk its
every quote, and his testimony that *"as we obey the Savior's voice and keep
our covenants — even by small and quiet sacrifices each day — we will feel His
love more deeply"* with it. So a closing is judged on what it says with the
formula set aside — which is done to weigh it, never to publish it, since every
quote here is the paragraph as it was given — and those that survive are ranked
**below everything else in their talk**. A talk with anything else to offer is
never quoted by its last line; a talk with nothing else still gets its turn.

**How many of a talk's best paragraphs are taken depends on who gave it.** The
prophet speaks to the whole Church a handful of times a year and those talks are
the ones members return to, so his talk gives up to **12**; a counselor in the
First Presidency **9**; a member of the Quorum of the Twelve **7**; everyone
else **3**. Every quota is several deep, so any talk with something to say is
heard from — no speaker who stood at that pulpit and taught goes unquoted,
however the scoring happened to fall.

A floor of 1.0 applies before any quota does, and it matters more than it looks:
a session's opening and closing are talks like any other to the filters above,
and without a floor their housekeeping — "welcome to general conference", "the
choir has just sung" — is exactly what a quota reaches down and takes. Better
that a strong quote comes round twice in six months than that one of those runs
once.

The pool is then shuffled and spread by speaker, so the same voice does not turn
up two days running. **The April 2026 conference yields 133 quotes from 34 talks
by 32 speakers**, so a quote comes round again about every four months. Raise
`--conferences` if you would rather trade freshness for variety.

### The same date always gives the same reading

Every day's pick is indexed from a **fixed epoch** — 1 January 2026 — rather
than from whenever the calendar was last built. A given date resolves to the
same reading no matter what span a build happens to cover, so a rebuild
part-way through the day never changes the verse under a reader who has already
seen it.

The mastery cadence is worked out the same way, from the date's distance from
the epoch rather than from a running count, and the ordinary days are numbered
with the mastery days taken out, so the curated tier is walked straight through
rather than skipping an entry every fortnight.

Scripture does not change, so the Book of Mormon calendar is stable for good.
The conference pool is stable until a new conference replaces it — which is the
point of it, and the one place a date's quote is expected to move.

## How it keeps itself current

### Following the Come, Follow Me curriculum automatically

Come, Follow Me rotates through the four standard works on a fixed cycle — Old
Testament, New Testament, Book of Mormon, Doctrine and Covenants — so a year's
manual is *derivable* rather than something to look up:

| 2026 | 2027 | 2028 | 2029 | 2030 |
| --- | --- | --- | --- | --- |
| Old Testament | New Testament | Book of Mormon | Doctrine and Covenants | Old Testament |

The builder derives each year's slug from that cycle and then **probes for it**,
the same way it handles conference: the cycle says which manual a year *should*
have, and only the site can say whether it is readable yet. An unpublished year
answers 404; one that is staged but still embargoed answers 401. Either way it is
left out and retried on the next refetch, so a new manual joins the calendar
within days of going public.

Because manuals tile contiguously — the 2026 manual ends December 27 and the
2027 manual's opening week starts December 28 — the years merge with no gap at
the January changeover. The builder covers two years by default (`--cfm-years`),
so next year's manual is already in the calendar long before it is needed.

Days past the last published manual simply have no Come, Follow Me card; it is
hidden rather than shown empty, and appears again as soon as a manual covering
those days is published and picked up.

### Following General Conference automatically

Conference is held early in April and early in October, and the talks are posted
over the following days. Two different things therefore decide which conference
to quote, and only one of them is a date:

- today's date says which session is the newest that *could* exist;
- only the site can say whether its text is up **yet**.

So the builder walks candidate sessions newest-first and takes the first one
that actually returns a full set of talks — at least 20, so a half-posted
conference is not chosen while it is still going up. A session that 404s or is
still appearing is treated as unavailable rather than assumed to arrive on a
fixed publication lag. Between conference weekend and the talks appearing, it
simply keeps quoting the previous conference; the changeover then happens on its
own within a few days, with no date to keep in step by hand.

The refetch runs Mondays and Thursdays, which bounds how long after publication
a new conference takes to show up.

### The speaker's photo

Every conference talk carries a photo of that speaker at the pulpit — the
picture the conference index uses as its thumbnail — and the quote card shows
it beneath the quote.

Those photos are **downloaded during the build and committed to
`assets/speakers/`**, not hot-linked. Hot-linking would have meant every page
view fetching an image from `churchofjesuschrist.org`, which is exactly the
runtime dependency the rest of the site avoids; a local copy keeps a page view
contacting nobody but the host serving the site, and keeps working offline and
from a `file://` URL.

The image URLs are IIIF, so the builder asks for the width it actually serves
(480px, just under twice the 272px the card displays it at) rather than taking
whatever size the page happened to link. That is currently 34 files and 767 KB —
one photo per talk that contributed a quote, fetched once and skipped on later
builds since a talk's photo never changes. A talk whose every paragraph was
filtered out can never be shown, so its photo is never downloaded. When a new
conference takes over the pool, photos no longer reachable from the calendar are
pruned in the same run.

A talk whose photo cannot be fetched simply gets no photo: the figure is
hidden, and the rest of the card is unchanged.

**The page never contacts `churchofjesuschrist.org` at runtime.** Nothing is
tracked or sent anywhere, and the only thing stored is a theme choice, in your
own browser, and only if you make one. If the Church's site changes shape, a
page view is unaffected; only a rebuild would notice.

## Light and dark

The page follows your system's light or dark setting on its own, as it always
has. A **Theme** button in the top corner is there for when you want the other
one anyway — it cycles Auto → Light → Dark → Auto, so an override is always
reversible back to simply following the system again.

A choice is remembered in `localStorage` under `theme` and applied by a short
inline script in `<head>`, before the page is first painted, so overriding a
dark system to light never flashes dark on the way in. Nothing else is stored,
and the entry is removed outright when you cycle back to Auto.

The button is hidden in the markup and revealed by the script, so with
JavaScript switched off you are not shown a control that cannot do anything —
the page just follows the system setting, exactly as before.

## Where a link lands

Every reference on a card links to the verse on `churchofjesuschrist.org`, and
for a long time it linked *at* the verse: `?lang=eng&id=p23#p23`, meaning
highlight verse 23 and scroll to verse 23. That is the obvious thing to write
and it puts the verse in the wrong place. The study reader offsets a fragment
landing by nothing at all — no `scroll-margin`, no `scroll-padding`, no script
that moves the scroll once the browser has jumped — so the browser does exactly
what it was asked and puts verse 23's first line flush against the top of the
window. The reader then draws its own chapter toolbar across that same strip.
You tap a reference and arrive at the verse with its opening line cut in half.

Nothing about that is fixable from this end — it is their page, their toolbar,
their stylesheet. The link is fixable, and the link is enough, because the
study reader reads the two halves of it separately: `id=` says what to
highlight, the fragment says where to scroll. Its own footnote links already
use them apart, as `?id=p21#note1_a`. So a card links like this:

```
https://www.churchofjesuschrist.org/study/scriptures/nt/rom/6?lang=eng&id=p23#p22
```

Highlight verse 23; scroll to verse 22. Verse 22 takes the toolbar's place at
the top of the screen, and verse 23 opens below it, whole and visible, with a
little of what comes before it for context. The highlight has not moved.

How far back to aim is a compromise between two ways of being wrong. Too little
and the toolbar still clips the verse; too much and the run-up above pushes the
verse off the bottom instead, which is worse — a verse cut off at the top is at
least visibly there. So the builder walks back through the verses actually
published above the one being quoted, adding up their length, and stops at
about two hundred characters, roughly six lines on a phone. In a chapter of
long verses that is one verse back. In a chapter of one-line verses it is two,
which is what keeps a two-line cushion from being no cushion at all.

Two cases get no cushion, for opposite reasons:

- **A verse that opens its chapter** gets no fragment at all, so the browser
  stays at the top of the page — which is where that verse already is, below
  the chapter heading rather than beneath the toolbar. Scrolling it to the top
  would be the one move guaranteed to clip it.
- **A verse whose neighbour above is long enough to fill the screen** keeps its
  own anchor and takes the clipping, because being cut off at the top beats
  starting below the bottom.

The verse above is the verse published above, which is not always the verse a
number below. A Joseph Smith Translation chapter prints only the verses it
changes, so JST Matthew 3 runs 4, 5, 6, 24, 25 — and a link to verse 24 scrolls
to verse 6, because verse 6 is what a reader sees above it on that page.

This applies to all three cards. The General Conference quote does the same
thing over a talk's paragraphs, whose ids are opaque (`p_ebRgS`) rather than
numbered, which is another reason the walk goes through the published order
instead of doing arithmetic on the reference.

`tools/test_links.py` holds it to this, and runs in CI before anything is
built — see [below](#checking-where-a-link-lands).

## Sharing a card

Each card has a **Share** button under it, which hands the reading to your own
share sheet — the same gesture the Gospel Library app uses, and the text lands
in the same shape, so one passed on from here sits in a thread beside one from
there without looking out of place:

```
A bishop who seeks to heal a troubled marriage or resolve a personal
controversy is working for peace.

President Dallin H. Oaks

https://www.churchofjesuschrist.org/study/general-conference/2026/04/49oaks?lang=eng&id=p_pRDHb#p_gQ2sf
```

The link is the official source on `churchofjesuschrist.org`, pointing at the
exact verse or paragraph — never at this site — so whoever receives it can read
it where it was published. It is the same link the card carries, aimed the same
way, so what a share opens to is what tapping the reference opens to (see
[Where a link lands](#where-a-link-lands)).

The sheet is your operating system's and the apps in it are yours; **this page
sends nothing anywhere and is never told what you shared, or with whom.** On a
desktop browser, which usually has no share sheet, the button copies the same
text to your clipboard instead and says so.

Each card is read at the moment its button is clicked, so if the script has
moved the page on to a new day (below), you share the reading actually in front
of you.

### With JavaScript switched off

A share sheet and a clipboard are both things only a script can ask for, so the
button is hidden in the markup and revealed by the script. In its place, baked
into the page, every card carries a **Share** disclosure that opens to the same
reading in the same shape, in a field ready to select and copy — into a mail
app, a message, a note, wherever you want to put it. Nothing is sent by the
page, and nothing goes anywhere at all until you press send in an app of your
own.

There are no app links above that field, and that is on purpose. Whether a
`mailto:` or `sms:` link does anything at all is settled after the page is out
of it, when the browser hands the address to your operating system — and if
that handoff declines, the page is never told. You press the link, and it just
sits there.

**Email this** was offered here for a while, `mailto:` being at least a
specified scheme, and it was found dead on a current phone all the same: a
Pixel 9 Pro on Android 17, Brave 1.93.130, scripts off. Markup cannot ask
whether the link will work, cannot be told that it didn't, and cannot fall back
to anything, so it is gone. A message link never got that far — a prefilled
body is only a custom, and not one both platforms share. Android reads
`sms:?body=`, iOS reads `sms:&body=`, and [Apple's own URL scheme
reference][sms-ref] says the address must not carry message text at all; the
`sms:?&body=` spelling that tries to satisfy both is the one a phone satisfying
neither does nothing whatsoever for.

On a page that promises to work without scripts, a link that quietly fails is
worse than a link that was never offered, so copying the field is the route to
all of those apps instead — select, copy, paste, and certain of it on every
phone there is.

Where the script does run it hides this block as it brings the button up, so
nobody is offered the same thing twice — and if the script never runs, or fails
to load, the block simply stays where it is.

[sms-ref]: https://developer.apple.com/library/archive/featuredarticles/iPhoneURLScheme_Reference/SMSLinks/SMSLinks.html

## It works with JavaScript switched off

`index.html` is generated from `tools/template.html` with the day's readings
**already written into the markup**, so the page is complete before any script
runs. With scripts disabled you get the full page — all three cards, every link,
and a way to share each of them (above).

The script is enhancement only. Apart from the theme button and swapping the
share block for a share sheet, it does nothing at all unless the reader's own
date has moved past the date the page was built for — someone ahead of the build
timezone, or looking at a copy served from cache. In that one case it swaps in
the right day from `data/daily.json`. If that fetch fails, the baked-in readings
stay put, the date shown next to them is the date they belong to, and a short
notice says which day the page is showing — so the page never claims a reading
is today's when it isn't.

Two scheduled runs of `.github/workflows/deploy.yml` keep it current:

- **daily**, at 08:10 UTC — the small hours in `America/Denver`, the timezone
  the page is built for. This re-renders the page for the new day from the
  calendar already in the repository, and fetches nothing.
- **Mondays and Thursdays**, at 09:00 UTC — a full refetch, to extend the
  calendar and pick up a newly published conference or manual.

Anything either run changes — `data/daily.json`, `index.html`, and the speaker
photos — is committed back to the repository, and then only the served files are
published to Pages.

Because the daily job is what moves a no-JavaScript page on to the next day, the
site depends on it running. The calendar is built two years ahead, so a missed
run costs you the right day, never the whole site.

## Running it yourself

```sh
python tools/build_daily.py              # refetch, rebuild the calendar, render index.html
python tools/build_daily.py --render-only  # just re-render today's page, no network
python -m http.server 8000               # then open http://localhost:8000
```

Python 3.9 or later, standard library only — there is nothing to install.

`index.html` is generated — **edit `tools/template.html`, not `index.html`.**

Opening the file straight off disk works for reading, since the readings are in
the markup; only the script's `fetch` is blocked on `file://` URLs, and it has
nothing to do when the page is already current.

Useful flags:

```sh
python tools/build_daily.py --days 1095              # build three years ahead
python tools/build_daily.py --start 2027-01-01       # start the calendar at a date
python tools/build_daily.py --conferences 4          # quote from the last four conferences
python tools/build_daily.py --timezone Europe/London # whose "today" the page is built for
python tools/build_daily.py --render-only --date 2026-12-25   # render a specific day
python tools/build_daily.py --cfm-years 3            # build a third year of manuals
python tools/build_daily.py \
    --manual come-follow-me-for-home-and-church-new-testament-2027 \
    --manual-year 2027                               # pin one manual, skipping the cycle
```

`--manual` is an override for testing; leave it alone and the four-year cycle
picks the manuals on its own.

`--timezone` and the daily cron in `.github/workflows/deploy.yml` need to agree;
change them together.

A full build makes about 1,100 requests and takes a few minutes on a cold
cache. Responses are memoised under `.cache/`; delete it to force a clean fetch.
Speaker photos are kept in `assets/speakers/` and are part of the site rather
than the cache — delete one and the next full build downloads it again.

### What a build says as it goes

It reports every decision above as it makes it: how many verses cleared the bar
and where the tier's cutoff landed, how many Come, Follow Me weeks came out with
citable verses and how many mastery passages were placed into them, any week
whose title did not name a reading, which conference was chosen, what was
skipped from it as church business, and how many quotes came out of how many
talks.

It closes on the calendar itself — the days it covers, its size on disk, how
many speaker photos are held and how many were pruned, and how many days have a
Come, Follow Me verse, with the span those days run over. That last date is the
one to read: it is when the card would go dark if no further manual were ever
published.

### Checking the rules that decide a reading

```sh
python tools/test_readings.py            # no network, no cache needed
```

The rules above are regular expressions over English, so they generalise in
ways nobody intended. A pattern written to refuse *And they rehearsed unto his
father* also refused *But this much I can tell you*; one written to keep Moroni
7:44 also kept 2 Nephi 2:7. `tools/readings_cases.json` holds the verses that
have been ruled on either way — the ones a reader judged, marked `*` in the
output, and the ones kept since as regression guards — and the test asserts the
rule still answers each of them the same way. It runs in CI before anything is
built or deployed.

**The verses in it are never typed by hand.** An earlier version of these cases
was, and a 2 Nephi 2:7 missing its closing clause passed a test that the verse
as published fails: the rule was wrong, the test agreed with it, and only a
sweep of the whole book caught it. To add a case, write the reference and the
verdict and let the API supply the words:

```sh
python tools/test_readings.py --refresh  # fill in every case's text from the study API
python tools/test_readings.py --verify   # confirm the committed text is still what is published
```

Both go through the same fetch and the same parser the builder uses, so what is
tested is what a card would show.

### Checking where a link lands

```sh
python tools/test_links.py               # no network, no cache needed
```

A link has to open its verse where a reader can actually see it, and there are
two ways to fail that: aim too close and the study reader's toolbar still clips
the verse, aim too far back and the run-up pushes the verse below the fold.
`tools/test_links.py` is written in those terms rather than in fragments — each
case says how much text a link may leave above its verse, so the test still
means something if the cushion is ever retuned, and it prints the fragment each
case produced so a change inside the bounds is still legible in the diff. It
runs in CI beside the reading rules.

A chapter is given to it as its verse *lengths* rather than its verse text,
because only the lengths decide where a link lands — which is also why this one
needs no committed corpus the way `test_readings.py` does.

## Licensing, and what the licence does not cover

The **code, styling and build tooling in this repository** are free software
under the [GNU Affero General Public License v3](LICENSE) or later.

The **scripture and General Conference text is not mine to license**, and
neither are the speaker photographs in `assets/speakers/`. They are published by
The Church of Jesus Christ of Latter-day Saints. The English text of the
standard works is in the public domain in the United States; General Conference
addresses and the conference photographs are © Intellectual Reserve, Inc., and
are reproduced here in short excerpts for personal, non-commercial study, with
every quotation linking back to the official source. The AGPL applies to this
project's own work only, and grants you no rights in the Church's content —
including the photographs, which are redistributed by this repository and are
the part of it most clearly not covered by that licence.

This site is not affiliated with, endorsed by, or produced by The Church of
Jesus Christ of Latter-day Saints. If you want to reuse Church content beyond
personal study, see <https://permissions.churchofjesuschrist.org/>.

https://bell-kevin.github.io/verse/

<p align="left"><a href="#readme-top">back to top</a></p>

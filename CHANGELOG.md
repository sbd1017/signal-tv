# Changelog

What changed in each release of Signal TV, newest first.

## v1.14.0 - 2026-10-20

- Faster and lighter: channels hand over at 10 s of picture or 5 segments, whichever first (6 s when converted) - 4K and converted channels start sooner; stereo AAC sound passed through instead of re-encoded; Live asks only for the channels whose programme changed since its copy of now/next (a few KB a minute, not ~180 KB); the newest films' and A-Z series' posters prepared daily for each site; three image resizes at once
- Public README: a Live demo section linking mubar.uk/signal (made-up provider, Classic in Settings, shared and reset nightly at 04:00)
- 4K channels with copied sound: the AAC framing MP4 segments need (aac_adtstoasc); the now/next update compares whole seconds with the guide's reload time
- Poster warm-up: a site that was restarting is tried again in 10 minutes, not the next day

## v1.13.0 - 2026-10-19

- Live: Also showing is back in view on desktop - one sideways row at every size, between what's on and the guide strip, counted when the picture is sized (a pinned column can't scroll to anything below the window)

## v1.12.0 - 2026-10-19

- Live on phones: Also showing is one sideways row with every channel, so the pinned player and its panel never run off the screen (the panel scrolls inside if it ever would)
- Site-wide sign-in: with SITE_AUTH=1 the app leaves sign-in to the site's central session (no device cookie); family sites keep their own passphrase under it (auth_request off), and their refused requests go to the site's handler only where nginx has one (family.sh switches the line on)

## v1.11.0 - 2026-10-18

- Live: the picture keeps its size when a channel starts (Also showing comes after the guide strip and never shrinks it); a 'live' channel that sends a short recording on repeat is stopped with a plain message, not restarted, and left out of Sports and Also showing for 6 hours (its backup tried first)

## v1.10.0 - 2026-10-17

- Docs: /tv-test preview removed 2026-10-17 (redirects to /tv); how to bring it back
- Library: each row's heading opens it as its own page, everything in a grid (Films, Series, Channels, Continue watching, Recently played); the mini player's corner button is a close (X), always showing

## v1.9.0 - 2026-10-17

- Classic: switch a channel to the backup provider (and back), the other channels showing the match being watched, a favourite star on film and series tiles, More like this under a title's details, the cast in the player (Settings: per device)
- Classic: team crests and competition logos on Sports (unlisted clubs' too) and the competition ESPN gives where the guide names none; Settings: Layout (open on / Sports tab, per device), Providers (the backup subscription) and Artwork (gaps, Add crest)

## v1.8.0 - 2026-10-16

- Sports artwork: guides' other spellings of listed clubs, show titles filtered, name variants share one crest
- Artwork gaps: close one whose own spelling has a crest by now
- Artwork: one short word ('Racing') never borrows another club's crest
- Live: the other channels showing the match being watched, under the player (change commentary without leaving Live)
- A backup provider for Live TV: the same channel from a second subscription when the main one won't play it
- Sports: SV Elversberg, Energie Cottbus and Fortuna Sittard, with the Greek guides' names for them
- Sports: Le Havre, Borac Banja Luka and Anorthosis Famagusta (with the guides' spellings, Greek ones too)
- Sports artwork: Borac Banja Luka's and Anorthosis' countries
- Sports: competitions the guide puts after the teams or names in Polish/Croatian, 3. Liga, Retro reruns as replays; ESPN for live/replay and the missing competition; bigger crests and competition marks on the board
- Sports board: the competition's name lines up under the teams' with or without a mark; a fixture verdict from another competition is another game; long single-word names smaller on phones, not broken
- Sports: Al Riyadh, the Saudi clubs' short names (Hilal, Nassr, Ittihad) and the Saudi league as Croatian and Portuguese guides write it
- Sports: the page gets each match's importance score (Live now ranked by it; it was never sent, so the earliest kick-off was featured); 'snimak' recordings and Racing Santander
- Sports: a city alone is the NFL/NBA side only against another of that league (college games were split per channel), countries and EuroLeague clubs as other languages write them, Paris Basketball, past-year and description-dated listings as replays, 'combate', a guide title repeated after its colon, long event titles kept to three lines
- Sports: a listing with no length (01:00-01:00) is one airing with its twins on other channels, not a card each
- README: the backup provider

## v1.7.0 - 2026-10-16

- Add a crest or logo by hand: Settings › Artwork › Add crest (image or link), and iptv artwork add
- Artwork gaps: a guide name's gap closes once that club's crest is found by name (or added)

## v1.6.0 - 2026-10-16

- Sports: a guide's short club name joins the full listing; feed codes aren't matches; channel-name markers dropped
- Crests for unlisted clubs: ESPN's club lists and Wikidata when TheSportsDB has nothing (or is down)

## v1.5.0 - 2026-10-16

- Cast in the player, from TMDB (optional): who's in the film or episode, with photos and characters

## v1.4.0 - 2026-10-16

- Films and Series tiles (grids and search): a favourite star in the poster's corner
- Public changelog: leave out housekeeping and changes later undone
- More like this on a series' or film's page
- More like this: the series index is also built at startup (from the saved catalogue)

## v1.3.0 - 2026-10-16

- Layout per device (Sports tab, the page it opens on); NFL nicknames when only the description names the sport
- Family sites keep their own copy in the browser: /tv's favourites no longer reach them
- Settings › Family sites: set a site's provider from the owner's page, checked with the provider first
- deploy/family.sh: the owner's Settings may POST a family site's provider (nginx method map, updated in place)
- Xtream: retry a failed call on a connection of its own (panels with a flaky server behind them)
- A new provider stops the refresh still fetching from the old one (it no longer waits behind a slow panel's download)

## v1.2.0 - 2026-10-15

- Family sites: other households' copies at their own address, behind one passphrase the owner sets
- deploy/family.sh: works with no sites yet, portable method-map edit, tested end to end against a temporary /etc
- Family sites: iptv family remove NAME (service, nginx entry tested first, interface, settings, data)
- Sports: live scores and the match minute on live cards (ESPN scoreboards), never on replays
- Live scores: a backup board, clubs matched by name, and replays caught by the real kick-off
- Your language for films and series; Classic gets Settings, the language choice and honest replays
- Sports: photos for fighters and badges for clubs the dataset doesn't know; wrap-up shows and F1 features aren't matches

## v1.1.0 - 2026-10-15

- The new interface goes live at /tv (default: new); docs and the public-copy trigger follow
- Sports: replays checked against the real fixture date, shown apart, never as LIVE
- Times in the Pi's zone by default, or this device's (Settings > Times)
- Settings > Times: shorter choice labels (London (the Pi) / This device (UTC))
- Sports: flags for national sides, Greek team names, more clubs, jump links; Films: English first
- Sports: EuroLeague clubs that are also football clubs count in basketball ("also:"), so their cards merge and show crests
- Sports: NBA and NFL teams, by city and nickname only in their own sport
- Sports: the replay check also covers basketball and NFL (a Sunday NFL game re-aired on a Thursday)

## v1.0.0 - 2026-10-15

- First release of Signal TV.

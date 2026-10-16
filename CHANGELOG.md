# Changelog

What changed in each release of Signal TV, newest first.

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

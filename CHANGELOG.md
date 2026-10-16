# Changelog

What changed in each release of Signal TV, newest first.

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

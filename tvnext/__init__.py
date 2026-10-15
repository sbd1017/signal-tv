"""Signal TV "next" sidecar: what the /tv-test interface needs beyond the live app.

- images: resized, cached derivatives of catalogue artwork (posters, backdrops, logos)
- sportsart: a persistent, cache-first library of team crests and competition logos

It runs as its own service (signal-tv-next.service, 127.0.0.1:8792) beside the live app and only
reads from it (the live app's image proxy on 127.0.0.1:8790). Nothing in tvapp/ or the live
service changes. Built so the modules can move into tvapp/ unchanged if /tv-test is promoted.
"""

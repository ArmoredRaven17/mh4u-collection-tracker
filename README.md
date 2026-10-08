# MH4U Collection Tracker

A web app for tracking your **Monster Hunter 4 Ultimate** equipment collection — every weapon and
armor piece, with an "owned" checkbox, full stats, crafting recipes and the upgrade tree.

**Live:** https://armoredraven17.github.io/mh4u-collection-tracker/ *(GitHub Pages, served from `docs/`)*

## Features

- All 14 weapon classes (2,308 weapons), Great Sword to Bow, including Charge Blade and Insect Glaive,
  and all five armor slots (3,074 pieces), Blademaster and Gunner.
- Click a cell to see stats: attack, affinity, element/status (with Awaken), defense, slots, price,
  sharpness (base and Sharpness +1), Hunting Horn notes and every song the horn can play, Gunlance
  shelling, Switch Axe and Charge Blade phials, the Insect Glaive's Kinsect, bowgun reload / recoil /
  deviation, ammo capacities, Rapid Fire and Crouching Fire, bow arc shot, charges and coatings;
  armor defense at every upgrade level, the Armor Sphere and zenny cost of each level, resistances
  and skills.
- The upgrade tree: what each weapon upgrades from and into, a crafting-routes view, and a
  checklist that costs a build along the tree.
- Progress per class and overall, filters (element, affinity, slots, rarity, class-specific
  stats), totals of everything still to craft.
- **Saved in your browser** automatically, with file save/load for backups or another device.
- The game's own icons, in its own Rare 1–10 colours: the equipment box icons in the slots and the detail panel, the
  class marks in the sidebar.

Not in this version: relic weapons and armor (the game rolls those at random), talismans and the
coating bottle icons.

## Where the data comes from

Everything is read from the game itself — a personally owned copy, extracted locally — by
[scripts/build_data.py](scripts/build_data.py): the weapon, armor, tree and recipe tables in the executable
(`exefs/code.decompressed.bin`), the English LMD text files for names and labels, and the icon
atlas. Each field was traced to the game code that reads it; the script comments give the
addresses. The method is the one used for the MH3U apps.

## Local development

There is no build step for the app. The stats are lazy-loaded with `fetch()`, which browsers block
on `file://`, so serve `docs/` over HTTP:

```
python -m http.server 8134 --directory docs
```

Then open http://localhost:8134/.

## Regenerating data

Needs a local MH4U extract laid out like `C:\MH4U-Extract` (romfs unpacked from the cart image,
the `core_common` ARC entries extracted to `arcx\`, `code.bin` decompressed), plus Python 3.10+,
Pillow, numpy and unicorn:

```
python scripts/build_data.py "C:\MH4U-Extract"
```

This rewrites `docs/data/`, `docs/assets/icons/` and `docs/assets/notes/`. Bump `DATA_VERSION` in
`docs/app.js` (and the `?v=` on `catalog.js` in `index.html`) whenever the data changes.

## Cache busting

GitHub Pages caches assets by full URL. When you change `styles.css`, `app.js` or
`data/catalog.js`, bump the `?v=N` query string on its tag in `index.html`.

## AI assistance

Most of this project's code — the app (ported from the author's MH3U Collection Tracker), the data
extraction and this README — was written with [Claude Code](https://claude.com/claude-code),
Anthropic's AI coding tool, working from the author's direction and reviewed before landing.
Commits made that way carry a `Co-Authored-By: Claude` trailer.

## Licensing

Code is MIT (see [LICENSE](LICENSE)). Game data and icons are Capcom's — see
[NOTICE.md](NOTICE.md). Monster Hunter 4 Ultimate is © Capcom Co., Ltd.; this is an unofficial fan
project.

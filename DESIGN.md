# Procto Design System

> Phase 1 source of truth for visual foundations. Machine-generated inputs:
> `design-system/procto/MASTER.md` (ui-ux-pro-max skill). This document is the
> human-maintained brief: it maps MASTER recommendations onto shadcn/ui token
> semantics and records every deviation with its reason.

## 1. Principles

1. **Semantic tokens only.** Components use `bg-primary`, `text-muted-foreground`, `text-success` — never raw hex or `dark:` overrides.
2. **States by default.** Every interactive element ships default / hover / focus-visible / disabled; async surfaces ship loading / error / empty.
3. **Presence and clarity.** Meeting UI is status-driven: mic, camera, network, speaking, and recording always have an explicit visual state — never color alone (icon/text carries meaning too).
4. **Accessible first.** WCAG 2.2 AA: 4.5:1 text contrast, visible focus rings, 44×44px touch targets for meeting controls, full keyboard operation, `prefers-reduced-motion` respected.
5. **Compose, don't reinvent.** shadcn/ui components are the primitive layer; domain components (`src/components/meeting/`) only compose them.

## 2. Color tokens

Light (`:root`) and dark (`.dark`) values live in `frontend/src/app/globals.css`.
All values verified against the adjacent surface for 4.5:1 text contrast.

| Token | Light | Dark | Usage |
|---|---|---|---|
| `background` | `#F5F3FF` | `#121124` | Page surface (indigo-tinted) |
| `foreground` | `#312E81` | `#EDEEFB` | Default text |
| `card` / `card-foreground` | `#FFFFFF` / `#312E81` | `#1A1936` / `#EDEEFB` | Cards, tiles |
| `popover` / `popover-foreground` | `#FFFFFF` / `#312E81` | `#1A1936` / `#EDEEFB` | Dialogs, dropdowns |
| `primary` / `primary-foreground` | `#4F46E5` / `#FFFFFF` | `#818CF8` / `#0B0A1F` | Primary buttons, links, active states |
| `secondary` / `secondary-foreground` | `#E8EAFB` / `#312E81` | `#24234A` / `#E4E6FF` | Secondary buttons, subtle fills |
| `muted` / `muted-foreground` | `#EBEFF9` / `#475569` | `#24234A` / `#A3A6CC` | Disabled surfaces, secondary text |
| `accent` / `accent-foreground` | `#EDEFFC` / `#312E81` | `#2A2A52` / `#E8EAFF` | Hover surface (menus, list rows) |
| `destructive` / `-foreground` | `#B91C1C` / `#FFFFFF` | `#F87171` / `#2C0A0A` | Leave/end meeting, errors |
| `success` / `-foreground` | `#047857` / `#FFFFFF` | `#34D399` / `#06281F` | Connected, recording-ready, joined |
| `warning` / `-foreground` | `#B45309` / `#FFFFFF` | `#FBBF24` / `#2A1A02` | Unstable network, raised hand |
| `info` / `-foreground` | `#1D4ED8` / `#FFFFFF` | `#60A5FA` / `#07162E` | Sharing screen, notifications |
| `border` / `input` | `#E0E7FF` / `#D6DBF6` | `white/10%` / `white/16%` | Dividers / form affordance |
| `ring` | `#6366F1` | `#818CF8` | Focus ring (≥3:1 non-text) |
| `chart-1…5` | `#6366F1 #818CF8 #059669 #F59E0B #312E81` | `#A5B4FC #818CF8 #34D399 #FBBF24 #C7D2FE` | Charts only |
| `sidebar*` | white surface | `#0F0E1F` surface | App shell navigation |

### Deviations from MASTER.md (and why)

| MASTER recommendation | Adopted | Reason |
|---|---|---|
| Primary `#6366F1` + on-primary `#000000` | `#4F46E5` + `#FFFFFF` (light) | `#6366F1` is only 4.04:1 on `#F5F3FF` as link text (fails AA). `#4F46E5` is 5.8:1 as text and 6.4:1 under white text. Brand hue unchanged; `#6366F1` retained as focus `ring` and `chart-1`. |
| Accent/CTA `#059669` mapped to shadcn `accent` | mapped to `success` token | shadcn's `accent` is the *hover surface* token (menu/list rows) — a green hover would be wrong. The CTA green becomes the `success` semantic pair (`#047857`/`#34D399`), which also carries meeting status meaning. |
| Destructive `#DC2626` | `#B91C1C` (light) | `#DC2626` drops to 4.1–4.4:1 as error text on `muted`/`background`. `#B91C1C` is ≥5.9:1 everywhere and still pure red. |
| Secondary `#818CF8` (solid pale indigo) | `#E8EAFB` surface (light) | shadcn `secondary` must read as a quiet surface (buttons, badges); a saturated fill competes with `primary`. `#818CF8` survives as dark `primary` and `chart-2`. |
| Google Fonts CSS `@import` | `next/font/google` (Lexend + Source Sans 3) | `next/font` self-hosts at build time: no third-party request, no layout shift. |
| — | Geist Mono kept for `font-mono` | MASTER defines no mono face; meeting codes/IDs need one. |

## 3. Typography

| Role | Face | Notes |
|---|---|---|
| Body | Source Sans 3 (`--font-sans`) | 16px base, line-height 1.5 |
| Headings | Lexend (`--font-heading`) | weights 300–700, use `font-heading` utility |
| Code/IDs | Geist Mono (`--font-mono`) | meeting codes, timestamps |

Scale (rem): `text-xs .75` · `text-sm .875` · `text-base 1` · `text-lg 1.125` ·
`text-xl 1.25` · `text-2xl 1.5` · `text-3xl 1.875` · `text-4xl 2.25`.
Minimum body size 12px; no gray-on-gray.

## 4. Spacing, radius, elevation

- Spacing: Tailwind's 4px scale only. MASTER `--space-*` maps to `gap-1 (4) gap-2 (8) gap-4 (16) gap-6 (24) gap-8 (32) gap-12 (48) gap-16 (64)`.
- Layout: `flex` + `gap-*` — never `space-x/y-*`.
- Radius: `--radius: 0.625rem` → buttons `rounded-md` (8px), cards `rounded-xl`, dialogs `rounded-2xl`.
- Elevation: `shadow-sm/md/lg/xl` overridden in `@theme` from MASTER's soft-shadow scale (slate-tinted so it works on both modes). Dark mode separates surfaces with `border-border`, not shadow.

## 5. Motion

- Duration band 150–300ms; ease-out for entrances, ease-in for exits; exits faster than entrances.
- Meaningful motion only (state change feedback, dialogs, speaking pulse). No layout-shifting transforms on hover.
- `prefers-reduced-motion: reduce` collapses all animation/transition durations globally (see `globals.css`).
- `shimmer` utility for live/loading text; `Skeleton` for layout placeholders.

## 6. Status semantics (meeting UI)

| State | Token | Icon accompanies color |
|---|---|---|
| Connected / joined / ready | `success` | check |
| Connecting / unstable network | `warning` | signal-low |
| Reconnecting / failed | `destructive` | alert-triangle |
| Screen sharing / info | `info` | monitor |
| Muted / camera off | `muted-foreground` | mic-off / video-off |
| Speaking | `ring` outline pulse | — |

Badges use tinted pairs (`bg-success/10 text-success border border-success/20`);
solid fills use `bg-success text-success-foreground`. Never `text-emerald-600`.

## 7. Component conventions

- shadcn/ui (`base-nova` style, **Base UI** primitives, lucide icons) via `npx shadcn@latest add`; components live in `src/components/ui/`, domain components in `src/components/meeting/`.
- `className` is for layout only; color/typography changes go through variants or tokens.
- Forms: `FieldGroup` + `Field` + `FieldLabel`; validation = `data-invalid` on `Field`, `aria-invalid` on control.
- Icons in buttons: `data-icon="inline-start|inline-end"`, no size classes.
- Overlays (`Dialog`, `Sheet`, `DropdownMenu`, `Tooltip`, `Popover`) own their stacking — no manual `z-index`.
- `Avatar` always has `AvatarFallback`; overlays always have a Title (or `sr-only`).
- Meeting controls: ≥44×44px, `aria-label` + tooltip with keyboard hint, `cursor-pointer`, visible focus ring.

## 8. Anti-patterns (forbidden)

Raw hex/`bg-blue-500` in components · manual `dark:` overrides · `space-x/y-*` ·
emojis as icons · icon-only buttons without labels · hidden focus rings ·
instant (0ms) state changes · layout-shifting hovers · horizontal scroll ·
placeholder-only form labels · color-only status.

## 9. Visual reference (Google Meet)

The UI in `reference/` (four Google Meet screenshots) is the layout/chrome target:
**structure and interaction patterns** come from Meet, **tokens, typography and brand**
stay Procto's (indigo, Lexend display, Source Sans 3, our status palette).

| Surface | Meet pattern adopted | Where |
|---|---|---|
| Home | Top bar: logo · join-by-code pill with inline **Join** · green **New** CTA · help/settings · avatar. Left icon rail (label under icon, tinted pill for active). Date header with week strip (today = filled circle). Centered empty state with primary CTA. | `src/app/page.tsx` |
| In-call top bar | Time · meet code (mono) · info button on the left; participant-count pill (avatar + count) on the right. | `meeting-top-bar.tsx` |
| Stage | Featured self tile + horizontal filmstrip of other participants. | `src/app/room/page.tsx` |
| Tile | Full-bleed surface; name chip overlaid bottom-left (Host/Hand badges inline); mic-off chip top-right; connection quality bottom-right; controls appear on hover/focus. | `participant-tile.tsx` |
| Control dock | Rounded-full pill, floating: mic · camera · share · reactions · chat · hand · kebab menu │ solid-red leave. Off-state toggles get a warning `!` badge. | `meeting-controls.tsx` |
| Utility cluster | Separate bottom-right pill: chat · people · host-lock (pressed states). | `UtilityCluster` |
| Reactions | Small pill of emoji reactions above the dock, collapsible. | `reaction-bar.tsx` |
| Side panels | Right-hand **People** (Add people · search · collapsible group · rows with role + mic + kebab) and **Chat** (messages switch · notice · list/empty · composer). | `meeting-panels.tsx` |

Rules while following the reference:

- Layout patterns only — every element still uses semantic tokens and our variants.
- Emojis appear **only** as reaction content (Meet-style), never as UI iconography.
- Interactions are demo-local (toasts, local state); no media or backend logic.

**Open question (carried to the report):** Meet's emoji reaction bar exists in the
reference but reactions are Phase 10 of the spec — the bar ships here as a visual
component only; confirm it should stay visible in Phase 1.

## 10. Pre-delivery checklist

- [ ] Tokens used, no raw colors in components
- [ ] Light **and** dark verified for contrast (4.5:1 text)
- [ ] Every control: hover / focus-visible / disabled / loading states
- [ ] Async surfaces: loading, error, empty, partial states
- [ ] Keyboard: reachable, operable, focus visible, dialogs titled
- [ ] Touch targets ≥44×44px for meeting controls
- [ ] Icons from lucide only; no emoji
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive at 375 / 768 / 1024 / 1440px, no horizontal scroll

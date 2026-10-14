# DESIGN.md: Abyss

## Summary

A dark, technical landing page held together by hairlines, with one luminous
object: a WebGL particle sphere. Dots stream into it and out of it continuously.
Everything else stays quiet so the sphere carries the energy.

The dark technical register of lambda.ai was the starting inspiration. This design
diverges from it deliberately in palette, header, hero composition, type treatment
and centrepiece.

## Principles

- **One luminous object.** The sphere is the only thing that glows or moves on its
  own. Type, rules and panels stay flat and still.
- **Sharp and flat.** Radius `0`, no shadows. Hairlines do the dividing.
- **Purple is the one accent.** It fills the call to action and leads the sphere's
  light. It never encodes meaning.
- **Sans for reading, mono for data.** Body copy, nav and buttons are Geist in
  sentence case. Geist Mono is kept for small labels, crawler tokens and step
  numbers.
- **The two audiences differ by weight, not hue.** Search is soft grey, AI is full
  white.

## Tokens

### Color

| Role | Value | Use |
|---|---|---|
| `ground` | `#05070B` | Page background, blue-black |
| `raised` | `#0C1219` | Panels, result card, input wells |
| `line` | `#1B2531` | Hairline rules |
| `line-strong` | `#56687C` | Control and input borders (3.5:1) |
| `text` | `#EAF2F8` | Primary text, AI readings, the white scan button |
| `text-soft` | `#A6B4C4` | Secondary text, Search readings |
| `text-mute` | `#8392A5` | Captions, step numbers |
| `accent` | `#6A45FF` | Purple: the "Book a call" buttons, focus ring |
| `accent-soft` | `#B3A6FF` | Light violet for small purple text, such as the eyebrow (9.4:1) |
| `accent-hover` | `#5A35EE` | Hover state of the purple buttons: darker, so the white label stays readable |
| `orb-1` / `orb-2` / `orb-3` | `#A58CFF` / `#5B7CFF` / `#EAF2F8` | The sphere: violet, blue, white |

Measured contrast on `ground`:

| Pair | Ratio |
|---|---|
| `text` on `ground` | 17.8:1 |
| `text-soft` on `ground` | 9.6:1 |
| `text-mute` on `ground` | 6.4:1 |
| white label on a purple button | 4.75:1 |
| purple focus ring against `ground` | 3.75:1 |

Purple buttons take white labels: a dark label on this purple is about 3:1 and
fails. Mid purple is too faint for small text on the ground, so small purple text
uses `accent-soft`. The sphere uses a lighter violet than the buttons, because
violet carries less light than cyan and the additive glow would otherwise read dim.

### Type

| Role | Face |
|---|---|
| Display | Geist 600, tracking `-0.03em` |
| Body, nav, buttons | Geist, sentence case |
| Labels and data | Geist Mono, small sizes only |

## Particle sphere (`ParticleSphere.tsx`)

The sphere is drawn in WebGL, and every particle's position is computed on the
GPU from time alone. The CPU only sets a handful of values per frame. It holds a
steady 60fps.

It has three populations:

| Population | Count | Behaviour | Colour |
|---|---|---|---|
| Shell | 6,000 | Dots spread evenly over the sphere. They breathe and turn | Mixed |
| Outbound | 3,500 | Peel off the surface and spiral outward, fading as they go | Violet and white |
| Inbound | 3,500 | Stream in from beyond the sphere and are absorbed at the surface | Mostly blue |

Moving particles carry short light trails. Each is a line from the particle back
along its path, bright at the head and fading behind, so the flow reads as motion
even in a still frame. Blending is additive, so where streams cross the surface
they flare.

**Placement:**

- On desktop, the sphere sits right of the headline in the hero. As the page
  scrolls it drifts to centre and dims to about 40%, so it stays behind every
  section without competing with paragraphs.
- On phones it sits low, behind the buttons, so the headline and paragraph stay
  clear.

**Other behaviour:**

- It leans gently toward the pointer.
- Under `prefers-reduced-motion` it renders a single still frame.
- Its colours are read from the `--color-orb-*` tokens, so a palette change reaches
  it without editing the component.

The canvas is opaque, cleared to the ground colour, and fixed at a negative
z-index. `<body>` must carry no background, or it paints over the canvas.

## Components

**Header.** One row inside the content width. The mark and wordmark sit left, nav
links sit in the centre, and a purple "Book a call" button sits right. It has a
translucent ground with backdrop blur and a hairline beneath.

**Mark.** A small sphere with one dot leaving its orbit: the hero's object, small.

**Buttons.**

| Class | Look | Use |
|---|---|---|
| `.btn-solid` | White | Run the scan |
| `.btn` | Purple | Book the call |
| `.btn-ghost` | Outline | Secondary actions |

All buttons use Geist in sentence case. The white button takes a dark label, the
purple button a white one.

**Hero.** The headline, paragraph and buttons are left-aligned on the left half of
the screen, and the sphere fills the right.

## Page order

1. Header
2. Hero: a light violet mono eyebrow, the headline, a paragraph, the scan button and a
   "Talk to us" outline button
3. Coverage: each engine with the crawler token it actually sends
4. The shift: then and now
5. The assistant: the chat scene
6. How it works: three steps numbered `01`, `02`, `03`
7. Questions
8. Closing call to action
9. Footer

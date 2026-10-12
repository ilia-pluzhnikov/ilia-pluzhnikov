<a href="https://ilia-pro-ai.com"><img src="assets/header.svg" width="100%" alt="Ilia Pluzhnikov. I build tools for Claude Code and teach teams to work with AI."></a>

<a href="https://ilia-pro-ai.com"><img src="assets/badges/site.svg" alt="Personal site: ilia-pro-ai.com"></a>&nbsp;&nbsp;<a href="https://www.youtube.com/@ilia-pluzhnikov"><img src="assets/badges/youtube.svg" alt="YouTube channel"></a>&nbsp;&nbsp;<a href="https://t.me/iliaprovse"><img src="assets/badges/telegram.svg" alt="Telegram channel"></a>

I started out as a product designer. For the last few years I have been teaching companies to work with AI, and building tools and products of my own along the way. Here are a few of them.

## claude-code-statusline

<a href="https://github.com/ilia-pluzhnikov/claude-code-statusline"><img src="assets/statusline.svg" width="100%" alt="The statusline with labels: model, folder and git, context used, prompt cache, 5-hour and 7-day limits"></a>

One line at the bottom of Claude Code with what you would otherwise have to ask for: the model and effort level, the folder and its git state, how much context is gone, whether the prompt cache is still warm, and how far you are into the 5-hour and 7-day limits.

It is one file of Node.js with no dependencies and no network calls. Colour carries the urgency, so the shape of the line tells you something before you read a number. One rule I care about: past 250k tokens the context bar turns yellow even in a 1M window, because that is where answers start to slip and long-context pricing begins.

<a href="https://github.com/ilia-pluzhnikov/claude-code-statusline"><img src="assets/badges/repository.svg" alt="claude-code-statusline on GitHub"></a>&nbsp;&nbsp;<a href="https://github.com/ilia-pluzhnikov/claude-code-statusline/stargazers"><img src="assets/badges/claude-code-statusline-stars.svg" alt="Stars"></a>&nbsp;&nbsp;<a href="https://github.com/ilia-pluzhnikov/claude-code-statusline/releases/latest"><img src="assets/badges/claude-code-statusline-release.svg" alt="Latest release"></a>

Install, in Claude Code:

```
/plugin marketplace add ilia-pluzhnikov/claude-code-statusline
/plugin install statusline-for-claude-code@ilia-pluzhnikov
/statusline-for-claude-code:setup
```

## Stargaze

<a href="https://github.com/ilia-pluzhnikov/stargaze"><img src="assets/stargaze.svg" width="100%" alt="Stargaze: skills drawn as constellations in a night sky"></a>

An RPG layer over real life. Each skill is a galaxy, every ability you master lights a star, and tasks become quests with XP, deadlines and rewards for finishing on time. Your AI agent joins as the game master: it proposes quests, accepts a result only with a note of what was done, and runs the reward economy.

One core with three ways in: the web sky, a CLI that agents call, and an HTTP API. Your world is a single JSON file on your own disk, so a backup is a file copy. I play it myself, with my own agent as the game master. The interface is in Russian for now.

<a href="https://github.com/ilia-pluzhnikov/stargaze"><img src="assets/badges/repository.svg" alt="Stargaze on GitHub"></a>&nbsp;&nbsp;<a href="https://github.com/ilia-pluzhnikov/stargaze/releases/latest"><img src="assets/badges/stargaze-release.svg" alt="Latest release"></a>

Run it with Docker:

```bash
docker run -d --name stargaze -p 127.0.0.1:8643:8643 \
  -v stargaze-data:/data ghcr.io/ilia-pluzhnikov/stargaze:latest
```

## book-distill

<a href="https://github.com/ilia-pluzhnikov/book-distill"><img src="assets/book-distill.svg" width="100%" alt="book-distill: a book goes through five extractors and three checks and comes out as three to seven skills"></a>

A Claude Code skill that turns a book, course or podcast into skills your agent can call, instead of a summary you read once. One book becomes three to seven small skills, one method each, with steps, the author's own example, and when not to use it.

Nothing is taken on faith. A method has to show up in two independent places in the source, answer a question the source never asks, and say something you would not hear without the book. Whatever fails goes to `rejected/` with the reason. At the end the new skills are called for real among every other skill on the machine, because a description that looks right on paper can still lose to a neighbour.

Built with Anton Vaskov ([@itpartypattaya](https://github.com/itpartypattaya)) on top of [cangjie-skill](https://github.com/kangarooking/cangjie-skill). The skill itself is written in Russian.

<a href="https://github.com/ilia-pluzhnikov/book-distill"><img src="assets/badges/repository.svg" alt="book-distill on GitHub"></a>&nbsp;&nbsp;<a href="https://github.com/ilia-pluzhnikov/book-distill/stargazers"><img src="assets/badges/book-distill-stars.svg" alt="Stars"></a>

Install:

```bash
git clone https://github.com/ilia-pluzhnikov/book-distill ~/.claude/skills/book-distill
```
